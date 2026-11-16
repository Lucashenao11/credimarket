"""Productos de ejemplo. Los ids 1..5 coinciden con las existencias de Inventario."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import Producto

PRODUCTOS_DEMO = [
    ("Portátil Lenovo IdeaPad 15", "computadores", 2_800_000),
    ("Portátil gamer ASUS TUF", "computadores", 5_400_000),   # id 2: última unidad
    ("Celular Samsung Galaxy A55", "celulares", 1_700_000),   # id 3: sin existencias
    ("Tablet Xiaomi Pad 6", "tablets", 1_300_000),
    ("Monitor LG 27 pulgadas", "monitores", 900_000),
]


def sembrar_demo(db: Session) -> None:
    if not settings.demo_datos or db.scalar(select(func.count()).select_from(Producto)):
        return
    for nombre, categoria, precio in PRODUCTOS_DEMO:
        db.add(Producto(nombre=nombre, categoria=categoria, precio_cop=precio))
    db.commit()
