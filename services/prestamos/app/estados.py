"""Máquina de estados del préstamo (tabla del enunciado + decisión D6)."""

from sqlalchemy import update
from sqlalchemy.orm import Session

from .models import HistorialEstado, Prestamo

RECHAZADA = "RECHAZADA"
PENDIENTE_INVENTARIO = "PENDIENTE_INVENTARIO"
APROBADA = "APROBADA"
CANCELADA_SIN_STOCK = "CANCELADA_SIN_STOCK"
COMPLETADA = "COMPLETADA"
CANCELADA = "CANCELADA"

# TODO(Lucas) PIEZA 1a: la tabla de transiciones. Clave = estado actual, valor = conjunto de estados
# a los que puede pasar (usa los nombres de las constantes de arriba y set() para los finales).
TRANSICIONES: dict[str, set[str]] = {
    PENDIENTE_INVENTARIO: {APROBADA, CANCELADA_SIN_STOCK, CANCELADA},
    APROBADA: {COMPLETADA, CANCELADA},
    RECHAZADA: set(),
    CANCELADA_SIN_STOCK: set(),
    CANCELADA: set(),
    COMPLETADA: set(),
}


class TransicionInvalida(Exception):
    pass


def cambiar_estado(
    db: Session, prestamo_id: str, esperado: str, nuevo: str, motivo: str | None = None
) -> bool:
    """Mueve el préstamo de `esperado` a `nuevo`. NO hace commit: lo hace quien llama.

    Devuelve True si cambió; False si el préstamo ya no estaba en `esperado`
    (otro proceso se le adelantó). Lanza TransicionInvalida si la tabla no permite el paso.
    """
    # TODO(Lucas) PIEZA 1b: tres pasos, en este orden
    #   1. Si `nuevo` no está permitido desde `esperado` -> raise TransicionInvalida(...)
    #   2. UPDATE condicional: solo cambia si el préstamo TODAVÍA está en `esperado`
    #      (mismo patrón que en Inventario). Si rowcount == 0 -> return False
    #   3. Insertar la fila de HistorialEstado y return True
    if nuevo not in TRANSICIONES[esperado]:
        raise TransicionInvalida(f"{esperado} -> {nuevo} no está permitido")
    resultado = db.execute(
        update(Prestamo)
        .where(Prestamo.id == prestamo_id, Prestamo.estado == esperado)
        .values(estado=nuevo, motivo=motivo)
    )
    if resultado.rowcount == 0:
        return False
    db.add(
        HistorialEstado(
            prestamo_id=prestamo_id,
            estado_anterior=esperado,
            estado_nuevo=nuevo,
            motivo=motivo,
        )
    )
    return True
