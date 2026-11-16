"""Timeout de PENDIENTE_INVENTARIO (decisión D6): si Inventario no responde, se cancela."""
import logging
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import estados, eventos
from .config import settings
from .db import SessionLocal
from .models import Prestamo

log = logging.getLogger("prestamos.timeouts")


def cancelar_pendientes_vencidos(db: Session, ahora: datetime | None = None) -> list[str]:
    ahora = ahora or datetime.now(timezone.utc)
    limite = ahora - timedelta(seconds=settings.timeout_inventario_segundos)
    ids = db.scalars(select(Prestamo.id).where(Prestamo.estado == estados.PENDIENTE_INVENTARIO,
                                               Prestamo.creado_en < limite)).all()
    return [i for i in ids if eventos.timeout_inventario(db, i) == "CANCELADA"]


def _ciclo(detener: threading.Event) -> None:
    while not detener.wait(5):
        try:
            with SessionLocal() as db:
                for prestamo_id in cancelar_pendientes_vencidos(db):
                    log.warning("Timeout de inventario: prestamo_id=%s cancelado", prestamo_id)
        except Exception:
            log.exception("Error revisando timeouts")


def iniciar(detener: threading.Event) -> None:
    threading.Thread(target=_ciclo, args=(detener,), daemon=True, name="timeouts").start()
