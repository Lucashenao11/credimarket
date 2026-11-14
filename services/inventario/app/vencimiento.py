"""Hilo que revisa periódicamente las reservas vencidas (decisión D6)."""
import logging
import threading

from .config import settings
from .db import SessionLocal
from .reservas import vencer_reservas

log = logging.getLogger("inventario.vencimiento")


def _ciclo(detener: threading.Event) -> None:
    while not detener.wait(settings.vencimiento_intervalo_segundos):
        try:
            with SessionLocal() as db:
                vencidas = vencer_reservas(db)
            for prestamo_id in vencidas:
                log.warning("Reserva vencida y liberada: prestamo_id=%s", prestamo_id)
        except NotImplementedError:
            pass  # mientras liberar no esté implementada
        except Exception:
            log.exception("Error revisando reservas vencidas")


def iniciar() -> threading.Event:
    detener = threading.Event()
    threading.Thread(target=_ciclo, args=(detener,), daemon=True, name="vencimiento").start()
    return detener
