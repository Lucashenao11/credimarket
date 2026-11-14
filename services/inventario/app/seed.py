"""Existencias de ejemplo para la demostración (solo si la tabla está vacía)."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import Existencia, Movimiento

# producto_id -> unidades. Los ids corresponden a los productos de ejemplo del servicio Productos.
EXISTENCIAS_DEMO = {1: 10, 2: 1, 3: 0, 4: 5, 5: 3}  # el producto 2 tiene la última unidad


def sembrar_demo(db: Session) -> None:
    if not settings.demo_datos or db.scalar(select(func.count()).select_from(Existencia)):
        return
    for producto_id, unidades in EXISTENCIAS_DEMO.items():
        db.add(Existencia(producto_id=producto_id, disponible=unidades, reservado=0))
        if unidades:
            db.add(Movimiento(producto_id=producto_id, tipo="ENTRADA", cantidad=unidades))
    db.commit()
