"""Lógica de negocio de Inventario: entradas, reservas, liberaciones, salidas y vencimientos.

Estas funciones no saben si las llama un endpoint HTTP o el consumidor de RabbitMQ:
el martes, el consumidor llamará a estas mismas funciones.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update  # noqa: F401  (update lo vas a necesitar)
from sqlalchemy.exc import IntegrityError  # noqa: F401  (lo vas a necesitar)
from sqlalchemy.orm import Session

from .config import settings
from .models import Existencia, Movimiento, Reserva


def ahora_utc() -> datetime:
    """Hora UTC sin zona horaria (así se guarda en la base)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Entradas (registro de unidades nuevas en bodega)
# ---------------------------------------------------------------------------


def registrar_entrada(db: Session, producto_id: int, cantidad: int) -> Existencia:
    if cantidad <= 0:
        raise ValueError("La cantidad de una entrada debe ser positiva")
    if db.get(Existencia, producto_id) is None:
        db.add(Existencia(producto_id=producto_id, disponible=0, reservado=0))
        db.flush()
    # Suma atómica en la base: no se lee el valor, se le suma directamente
    db.execute(
        update(Existencia)
        .where(Existencia.producto_id == producto_id)
        .values(disponible=Existencia.disponible + cantidad)
    )
    db.add(Movimiento(producto_id=producto_id, tipo="ENTRADA", cantidad=cantidad))
    db.commit()
    return db.get(Existencia, producto_id, populate_existing=True)


# ---------------------------------------------------------------------------
# Reservar  —  pieza crítica (pruebas de aceptación 3, 4 y 5)
# ---------------------------------------------------------------------------


def reservar(db: Session, prestamo_id: str, producto_id: int, cantidad: int) -> str:
    """Aparta unidades para un préstamo. Devuelve "RESERVADA", "INSUFICIENTE" o "YA_PROCESADA".

    TODO(Lucas): escribe esta función (unas 15 líneas). La variable vence_en ya está calculada.

    Requisitos:
      1. Si hay unidades suficientes: moverlas de `disponible` a `reservado`, crear la Reserva
         (estado "ACTIVA", con vence_en) y un Movimiento de tipo "RESERVA". Devolver "RESERVADA".
      2. Si NO hay unidades suficientes (o el producto no existe): no modificar nada y
         devolver "INSUFICIENTE".
      3. Si ya existe una reserva para este prestamo_id (mensaje repetido): no modificar nada
         y devolver "YA_PROCESADA". Las unidades no se pueden descontar dos veces.
      4. Correcto aunque dos préstamos pidan la última unidad al mismo tiempo: solo uno la obtiene.

    Piezas que tienes:
      - Actualización condicional: la verificación va DENTRO del UPDATE.
            resultado = db.execute(
                update(Existencia)
                .where(<condición 1>, <condición 2>)
                .values(<columna>=<expresión>, <columna>=<expresión>)
            )
        Para restar en la base usa la columna misma: Existencia.disponible - cantidad
      - resultado.rowcount dice cuántas filas modificó el UPDATE: 1 si reservó, 0 si no.
      - Si rowcount es 0: db.rollback() y devolver "INSUFICIENTE".
      - Reserva(...) y Movimiento(...) se crean con argumentos con nombre (mira models.py).
      - Si la Reserva repite el prestamo_id, db.commit() lanza IntegrityError (UNIQUE).
        Ojo: el rollback deshace TODO lo de esta transacción, incluido el UPDATE de existencias.
    """
    vence_en = ahora_utc() + timedelta(
        seconds=settings.reserva_ttl_segundos
    )  # noqa: F841

    resultado = db.execute(
        update(Existencia)
        .where(Existencia.producto_id == producto_id, Existencia.disponible >= cantidad)
        .values(
            disponible=Existencia.disponible - cantidad,
            reservado=Existencia.reservado + cantidad,
        )
    )

    if resultado.rowcount == 0:
        db.rollback()
        return "INSUFICIENTE"

    db.add(
        Reserva(
            prestamo_id=prestamo_id,
            producto_id=producto_id,
            cantidad=cantidad,
            estado="ACTIVA",
            vence_en=vence_en,
        )
    )
    db.add(
        Movimiento(
            producto_id=producto_id,
            tipo="RESERVA",
            cantidad=cantidad,
            prestamo_id=prestamo_id,
        )
    )

    try:
        db.commit()
        return "RESERVADA"
    except IntegrityError:
        db.rollback()
        return "YA_PROCESADA"


# ---------------------------------------------------------------------------
# Liberar  —  pieza crítica (prueba de aceptación 7)
# ---------------------------------------------------------------------------


def liberar(
    db: Session,
    prestamo_id: str,
    estado_final: str = "LIBERADA",
    motivo: str | None = None,
) -> str:
    """Devuelve a `disponible` las unidades de una reserva ACTIVA.

    Devuelve "LIBERADA" (o el estado_final que se pida), "NO_EXISTE" o "YA_FINALIZADA".
    estado_final es "LIBERADA" para una cancelación y "VENCIDA" cuando se usa desde
    vencer_reservas. El tipo de Movimiento es "LIBERACION" o "VENCIMIENTO", respectivamente.

    TODO(Lucas): escribe esta función (unas 15 líneas).

    Requisitos:
      1. Si no hay reserva para ese prestamo_id: devolver "NO_EXISTE".
      2. Si la reserva ya no está ACTIVA (ya liberada, confirmada o vencida): no modificar
         nada y devolver "YA_FINALIZADA". Liberar dos veces no puede devolver unidades dos veces.
      3. Si está ACTIVA: cambiarla a estado_final (con el motivo), mover sus unidades de
         `reservado` a `disponible` y crear el Movimiento. Devolver estado_final.
      4. Correcto aunque dos cancelaciones del mismo préstamo lleguen al mismo tiempo.

    Pista: el requisito 4 se resuelve con la MISMA idea que reservar, pero aplicada al
    estado de la reserva: un UPDATE de reservas que solo cambia la fila si estado == "ACTIVA".
    Para obtener la reserva: db.scalar(select(Reserva).where(Reserva.prestamo_id == prestamo_id))
    """

    reserva = db.scalar(select(Reserva).where(Reserva.prestamo_id == prestamo_id))

    if reserva is None:
        return "NO_EXISTE"

    cambio = db.execute(
        update(Reserva)
        .where(Reserva.id == reserva.id, Reserva.estado == "ACTIVA")
        .values(estado=estado_final, motivo=motivo)
    )

    if cambio.rowcount == 0:
        db.rollback()
        return "YA_FINALIZADA"

    db.execute(
        update(Existencia)
        .where(Existencia.producto_id == reserva.producto_id)
        .values(
            disponible=Existencia.disponible + reserva.cantidad,
            reservado=Existencia.reservado - reserva.cantidad,
        )
    )

    tipo = "VENCIMIENTO" if estado_final == "VENCIDA" else "LIBERACION"

    db.add(
        Movimiento(
            producto_id=reserva.producto_id,
            tipo=tipo,
            cantidad=reserva.cantidad,
            prestamo_id=reserva.prestamo_id,
        )
    )
    
    db.commit()
    return estado_final


# ---------------------------------------------------------------------------
# Confirmar salida (entrega simulada)
# ---------------------------------------------------------------------------


def confirmar_salida(db: Session, prestamo_id: str) -> str:
    """Las unidades reservadas salen de la bodega. Devuelve "CONFIRMADA", "NO_EXISTE" o "YA_FINALIZADA"."""
    reserva = db.scalar(select(Reserva).where(Reserva.prestamo_id == prestamo_id))
    if reserva is None:
        return "NO_EXISTE"
    # Cambio de estado condicional: solo una de dos confirmaciones simultáneas lo logra
    cambio = db.execute(
        update(Reserva)
        .where(Reserva.id == reserva.id, Reserva.estado == "ACTIVA")
        .values(estado="CONFIRMADA")
    )
    if cambio.rowcount == 0:
        db.rollback()
        return "YA_FINALIZADA"
    db.execute(
        update(Existencia)
        .where(Existencia.producto_id == reserva.producto_id)
        .values(reservado=Existencia.reservado - reserva.cantidad)
    )
    db.add(
        Movimiento(
            producto_id=reserva.producto_id,
            tipo="SALIDA",
            cantidad=reserva.cantidad,
            prestamo_id=prestamo_id,
        )
    )
    db.commit()
    return "CONFIRMADA"


# ---------------------------------------------------------------------------
# Vencimiento de reservas (lo ejecuta un hilo cada pocos segundos)
# ---------------------------------------------------------------------------


def vencer_reservas(db: Session, ahora: datetime | None = None) -> list[str]:
    """Libera las reservas ACTIVAS cuyo vence_en ya pasó. Devuelve los prestamo_id vencidos.

    El martes, por cada uno se publicará el evento ReservaVencida hacia Préstamos.
    """
    ahora = ahora or ahora_utc()
    candidatos = db.scalars(
        select(Reserva.prestamo_id).where(
            Reserva.estado == "ACTIVA", Reserva.vence_en < ahora
        )
    ).all()
    vencidas = []
    for prestamo_id in candidatos:
        # Reutiliza liberar: si justo antes alguien la confirmó o liberó, devuelve YA_FINALIZADA
        if (
            liberar(db, prestamo_id, estado_final="VENCIDA", motivo="RESERVA_VENCIDA")
            == "VENCIDA"
        ):
            vencidas.append(prestamo_id)
    return vencidas
