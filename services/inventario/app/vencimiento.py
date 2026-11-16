"""Hilo que revisa periódicamente las reservas vencidas (decisión D6) y avisa a Préstamos."""
import logging
import threading

from sqlalchemy import exists, literal, select
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal
from .mensajeria import Outbox, encolar
from .models import Reserva
from .reservas import vencer_reservas

log = logging.getLogger("inventario.vencimiento")


def emitir_vencidas(db: Session) -> list[str]:
    """Encola ReservaVencida por cada reserva VENCIDA que todavía no la tiene.

    Se basa en el ESTADO de la reserva (no en lo que devolvió vencer_reservas): así, aunque el
    servicio caiga entre liberar y encolar, el aviso se emite en el ciclo siguiente. El id del
    mensaje es determinista ('vencida-<prestamo_id>'), por lo que nunca se duplica.
    """
    ya_emitida = exists(select(Outbox.id).where(Outbox.id == literal("vencida-") + Reserva.prestamo_id))
    pendientes = db.scalars(select(Reserva.prestamo_id).where(Reserva.estado == "VENCIDA", ~ya_emitida)).all()
    for prestamo_id in pendientes:
        encolar(db, "reserva.vencida", "ReservaVencida", {"prestamo_id": prestamo_id},
                message_id=f"vencida-{prestamo_id}")
    db.commit()
    return list(pendientes)


def _ciclo(detener: threading.Event) -> None:
    while not detener.wait(settings.vencimiento_intervalo_segundos):
        try:
            with SessionLocal() as db:
                vencer_reservas(db)
            with SessionLocal() as db:
                for prestamo_id in emitir_vencidas(db):
                    log.warning("Reserva vencida y liberada: prestamo_id=%s", prestamo_id)
        except NotImplementedError:
            pass  # mientras liberar no esté implementada
        except Exception:
            log.exception("Error revisando reservas vencidas")


def iniciar() -> threading.Event:
    detener = threading.Event()
    threading.Thread(target=_ciclo, args=(detener,), daemon=True, name="vencimiento").start()
    return detener
