from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Producto
from ..schemas import CotizacionOut, ProductoIn, ProductoOut, ProductoUpdate
from ..security import requiere_rol, usuario_actual

router = APIRouter(tags=["productos"])
SOLO_ADMIN = Depends(requiere_rol("admin"))


def _o_404(db: Session, producto_id: int) -> Producto:
    producto = db.get(Producto, producto_id)
    if producto is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto no encontrado")
    return producto


@router.get("/productos", response_model=list[ProductoOut], dependencies=[Depends(usuario_actual)])
def listar(solo_activos: bool = True, db: Session = Depends(get_db)):
    consulta = select(Producto).order_by(Producto.id)
    if solo_activos:
        consulta = consulta.where(Producto.activo.is_(True))
    return db.scalars(consulta).all()


@router.get("/productos/{producto_id}", response_model=ProductoOut,
            dependencies=[Depends(usuario_actual)])
def consultar(producto_id: int, db: Session = Depends(get_db)):
    # TODO(compañero): cache-aside con Redis. Primero Redis; si falla o no está, la base.
    return _o_404(db, producto_id)


@router.post("/productos", response_model=ProductoOut, status_code=201, dependencies=[SOLO_ADMIN])
def crear(datos: ProductoIn, db: Session = Depends(get_db)):
    producto = Producto(**datos.model_dump())
    db.add(producto)
    db.commit()
    return producto


@router.put("/productos/{producto_id}", response_model=ProductoOut, dependencies=[SOLO_ADMIN])
def actualizar(producto_id: int, datos: ProductoUpdate, db: Session = Depends(get_db)):
    producto = _o_404(db, producto_id)
    cambios = datos.model_dump(exclude_unset=True)
    if cambios:
        for campo, valor in cambios.items():
            setattr(producto, campo, valor)
        producto.version += 1
        db.commit()
        # TODO(compañero): invalidar la clave en Redis DESPUÉS del commit
    return producto


@router.delete("/productos/{producto_id}", response_model=ProductoOut, dependencies=[SOLO_ADMIN])
def desactivar(producto_id: int, db: Session = Depends(get_db)):
    producto = _o_404(db, producto_id)
    if producto.activo:
        producto.activo = False
        producto.version += 1
        db.commit()
        # TODO(compañero): invalidar la clave en Redis DESPUÉS del commit
    return producto


@router.get("/productos/{producto_id}/cotizacion", response_model=CotizacionOut,
            dependencies=[Depends(usuario_actual)])
def cotizacion(producto_id: int, db: Session = Depends(get_db)):
    """Fuente de verdad para el monto del préstamo: SIEMPRE lee de PostgreSQL, nunca de Redis."""
    p = _o_404(db, producto_id)
    return CotizacionOut(producto_id=p.id, nombre=p.nombre, precio_cop=int(p.precio_cop),
                         version=p.version, activo=p.activo, consultado_en=datetime.now(timezone.utc))
