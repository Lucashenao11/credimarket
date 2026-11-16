"""Consumidor de Inventario: comandos de Préstamos (cola inventario.comandos).

Cada mensaje trae un message_id. Regla de oro: el efecto, la respuesta (outbox) y el registro
de "mensaje visto" (inbox) se confirman en UN SOLO commit. Y el ack lo da mensajeria.py DESPUÉS.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .mensajeria import encolar, marcar_procesado, ya_procesado  # noqa: F401
from .models import Reserva
from .reservas import confirmar_salida, liberar, reservar


def _estado_reserva(db: Session, prestamo_id: str) -> str | None:
    return db.scalar(
        select(Reserva.estado)
        .where(Reserva.prestamo_id == prestamo_id)
        .execution_options(populate_existing=True)
    )


def procesar_reserva_solicitada(db: Session, mensaje: dict) -> str:
    """ReservaSolicitada -> reserva atómica -> responde InventarioReservado o InventarioInsuficiente.

    TODO(Lucas) PIEZA B (consumidor idempotente). Pasos, en este orden:
      1. Llama a reservar(db, prestamo_id, producto_id, cantidad) con los datos de mensaje["payload"].
      2. Decide la respuesta y encólala con encolar(db, routing_key, tipo, {"prestamo_id": ...}):
           - resultado "INSUFICIENTE"  -> "inventario.insuficiente", "InventarioInsuficiente"
           - si no (RESERVADA o YA_PROCESADA): responde "inventario.reservado", "InventarioReservado"
             SOLO si _estado_reserva(db, prestamo_id) == "ACTIVA". Si la reserva ya está liberada,
             vencida o confirmada, responder 'reservado' sería mentira: no se encola nada.
      3. Registra el mensaje como visto: marcar_procesado(db, mensaje)
      4. db.commit() para confirmar respuesta + registro JUNTOS.
         Si el commit lanza IntegrityError, otro proceso ya procesó este message_id:
         db.rollback() y devuelve "DUPLICADO" (la respuesta encolada se deshace con él).
      5. Devuelve el resultado de reservar.
    """
    p = mensaje["payload"]
    resultado = reservar(db, p["prestamo_id"], p["producto_id"], p["cantidad"])
    if resultado == "INSUFICIENTE":
        encolar(
            db,
            "inventario.insuficiente",
            "InventarioInsuficiente",
            {"prestamo_id": p["prestamo_id"]},
        )
    elif _estado_reserva(db, p["prestamo_id"]) == "ACTIVA":
        encolar(
            db,
            "inventario.reservado",
            "InventarioReservado",
            {"prestamo_id": p["prestamo_id"]},
        )
        marcar_procesado(db, mensaje)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return "DUPLICADO"
    return resultado


def _liberar_reserva(db: Session, mensaje: dict) -> str:
    resultado = liberar(
        db, mensaje["payload"]["prestamo_id"], motivo=mensaje["payload"].get("motivo")
    )
    return _cerrar(db, mensaje, resultado)


def _confirmar_salida(db: Session, mensaje: dict) -> str:
    prestamo_id = mensaje["payload"]["prestamo_id"]
    resultado = confirmar_salida(db, prestamo_id)
    # Si el mensaje se redeliveró tras una caída entre el commit de la salida y este punto, el
    # resultado es YA_FINALIZADA pero la reserva figura CONFIRMADA: igual hay que avisar a Préstamos.
    if resultado == "CONFIRMADA" or (
        resultado == "YA_FINALIZADA"
        and _estado_reserva(db, prestamo_id) == "CONFIRMADA"
    ):
        encolar(
            db, "salida.confirmada", "SalidaConfirmada", {"prestamo_id": prestamo_id}
        )
    return _cerrar(db, mensaje, resultado)


def _cerrar(db: Session, mensaje: dict, resultado: str) -> str:
    marcar_procesado(db, mensaje)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return "DUPLICADO"
    return resultado


def manejar_comando(db: Session, mensaje: dict) -> str:
    if ya_procesado(db, mensaje["message_id"]):
        return "DUPLICADO"
    tipo = mensaje["tipo"]
    if tipo == "ReservaSolicitada":
        return procesar_reserva_solicitada(db, mensaje)
    if tipo == "LiberarReserva":
        return _liberar_reserva(db, mensaje)
    if tipo == "ConfirmarSalida":
        return _confirmar_salida(db, mensaje)
    return _cerrar(db, mensaje, "TIPO_DESCONOCIDO")
