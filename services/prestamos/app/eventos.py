"""Qué hace Préstamos al recibir cada respuesta de Inventario (y al cancelar / entregar).
Las llama el consumidor de RabbitMQ (consumidor.py) y los endpoints. Cada función hace su propio
commit y devuelve un texto que dice qué decidió. Todas son idempotentes: repetir una no cambia nada.
"""
from sqlalchemy.orm import Session

from . import estados as e
from .mensajeria import encolar
from .models import Prestamo


def _liberar(db: Session, prestamo_id: str, motivo: str) -> None:
    """Encola LiberarReserva (sin commit: va en la transacción de quien lo llama)."""
    encolar(db, "reserva.liberar", "LiberarReserva", {"prestamo_id": prestamo_id, "motivo": motivo})


def _mover(db: Session, prestamo_id: str, desde: str, hacia: str, motivo: str | None = None,
           liberar: bool = False) -> bool:
    """Cambio de estado + (opcional) LiberarReserva, confirmados JUNTOS en una transacción."""
    ok = e.cambiar_estado(db, prestamo_id, desde, hacia, motivo)
    if ok:
        if liberar:
            _liberar(db, prestamo_id, motivo or hacia)
        db.commit()
    else:
        db.rollback()
    return ok


def _leer(db: Session, prestamo_id: str) -> Prestamo | None:
    return db.get(Prestamo, prestamo_id, populate_existing=True)


def reserva_confirmada(db: Session, prestamo_id: str) -> str:
    p = _leer(db, prestamo_id)
    if p is None:
        return "IGNORADO_DESCONOCIDO"
    if p.estado == e.PENDIENTE_INVENTARIO and _mover(db, prestamo_id, e.PENDIENTE_INVENTARIO, e.APROBADA):
        return "APROBADA"
    p = _leer(db, prestamo_id)
    if p.estado in (e.APROBADA, e.COMPLETADA):
        return "DUPLICADO"  # mensaje repetido: ya se procesó
    # Evento tardío (D6): el préstamo ya está cancelado o rechazado. NUNCA se reactiva;
    # la reserva que Inventario hizo hay que devolverla.
    _liberar(db, prestamo_id, "EVENTO_TARDIO")
    db.commit()
    return "LIBERAR_RESERVA"


def inventario_insuficiente(db: Session, prestamo_id: str) -> str:
    if _mover(db, prestamo_id, e.PENDIENTE_INVENTARIO, e.CANCELADA_SIN_STOCK, "SIN_STOCK"):
        return "CANCELADA_SIN_STOCK"
    return "IGNORADO"


def reserva_vencida(db: Session, prestamo_id: str) -> str:
    # Inventario ya liberó las unidades: aquí NO se publica LiberarReserva.
    for desde in (e.APROBADA, e.PENDIENTE_INVENTARIO):
        if _mover(db, prestamo_id, desde, e.CANCELADA, "RESERVA_VENCIDA"):
            return "CANCELADA"
    return "IGNORADO"


def timeout_inventario(db: Session, prestamo_id: str) -> str:
    # liberar=True: por si Inventario respondió justo tarde y ya había reservado
    if _mover(db, prestamo_id, e.PENDIENTE_INVENTARIO, e.CANCELADA, "TIMEOUT_INVENTARIO", liberar=True):
        return "CANCELADA"
    return "IGNORADO"


def salida_confirmada(db: Session, prestamo_id: str) -> str:
    return "COMPLETADA" if _mover(db, prestamo_id, e.APROBADA, e.COMPLETADA) else "IGNORADO"


def cancelar(db: Session, prestamo_id: str) -> str:
    """Cancelación pedida por el cliente o el administrador, antes de la entrega.
    El estado pasa a CANCELADA y LiberarReserva queda en el outbox EN LA MISMA transacción."""
    for desde in (e.APROBADA, e.PENDIENTE_INVENTARIO):
        if _mover(db, prestamo_id, desde, e.CANCELADA, "CANCELADO_POR_USUARIO", liberar=True):
            return "CANCELADA"
    return "NO_CANCELABLE"


def solicitar_entrega(db: Session, prestamo_id: str) -> str:
    """La entrega es una orden a Inventario; COMPLETADA llega cuando Inventario confirme la salida."""
    p = _leer(db, prestamo_id)
    if p is None or p.estado != e.APROBADA:
        return "NO_ENTREGABLE"
    encolar(db, "salida.confirmar", "ConfirmarSalida", {"prestamo_id": prestamo_id})
    db.commit()
    return "ENTREGA_SOLICITADA"


MANEJADORES = {
    "InventarioReservado": reserva_confirmada,
    "InventarioInsuficiente": inventario_insuficiente,
    "ReservaVencida": reserva_vencida,
    "TimeoutInventario": timeout_inventario,
    "SalidaConfirmada": salida_confirmada,
}
