"""Qué hace Préstamos al recibir cada respuesta de Inventario.
Hoy se invoca desde un endpoint de pruebas; el martes lo llamará el consumidor de RabbitMQ.
Cada función hace su propio commit y devuelve un texto que dice qué decidió.
"""
from sqlalchemy.orm import Session

from . import estados as e
from .models import Prestamo


def _mover(db: Session, prestamo_id: str, desde: str, hacia: str, motivo: str | None = None) -> bool:
    ok = e.cambiar_estado(db, prestamo_id, desde, hacia, motivo)
    if ok:
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
    # TODO(broker, martes): publicar LiberarReserva (outbox) en esta rama.
    return "LIBERAR_RESERVA"


def inventario_insuficiente(db: Session, prestamo_id: str) -> str:
    if _mover(db, prestamo_id, e.PENDIENTE_INVENTARIO, e.CANCELADA_SIN_STOCK, "SIN_STOCK"):
        return "CANCELADA_SIN_STOCK"
    return "IGNORADO"


def reserva_vencida(db: Session, prestamo_id: str) -> str:
    for desde in (e.APROBADA, e.PENDIENTE_INVENTARIO):
        if _mover(db, prestamo_id, desde, e.CANCELADA, "RESERVA_VENCIDA"):
            return "CANCELADA"
    return "IGNORADO"


def timeout_inventario(db: Session, prestamo_id: str) -> str:
    if _mover(db, prestamo_id, e.PENDIENTE_INVENTARIO, e.CANCELADA, "TIMEOUT_INVENTARIO"):
        # TODO(broker, martes): publicar LiberarReserva por si Inventario respondió justo tarde
        return "CANCELADA"
    return "IGNORADO"


def salida_confirmada(db: Session, prestamo_id: str) -> str:
    return "COMPLETADA" if _mover(db, prestamo_id, e.APROBADA, e.COMPLETADA) else "IGNORADO"


MANEJADORES = {
    "InventarioReservado": reserva_confirmada,
    "InventarioInsuficiente": inventario_insuficiente,
    "ReservaVencida": reserva_vencida,
    "TimeoutInventario": timeout_inventario,
    "SalidaConfirmada": salida_confirmada,
}
