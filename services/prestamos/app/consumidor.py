"""Consumidor de Préstamos: respuestas de Inventario (cola prestamos.eventos)."""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import eventos
from .mensajeria import marcar_procesado, ya_procesado


def manejar_evento(db: Session, mensaje: dict) -> str:
    """Procesa un mensaje UNA sola vez (por message_id). Los manejadores de eventos.py ya son
    idempotentes por el UPDATE condicional; el inbox evita reprocesar y deja trazabilidad."""
    if ya_procesado(db, mensaje["message_id"]):
        return "DUPLICADO"
    manejador = eventos.MANEJADORES.get(mensaje["tipo"])
    resultado = "TIPO_DESCONOCIDO" if manejador is None else manejador(db, mensaje["payload"]["prestamo_id"])
    marcar_procesado(db, mensaje)
    try:
        db.commit()
    except IntegrityError:  # otro proceso procesó el mismo mensaje al mismo tiempo
        db.rollback()
        return "DUPLICADO"
    return resultado
