import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cache import HIT, MISS, CacheProductos
from ..db import get_db
from ..models import Producto
from ..schemas import CotizacionOut, ProductoIn, ProductoOut, ProductoUpdate
from ..security import requiere_rol, usuario_actual

router = APIRouter(tags=["productos"])
SOLO_ADMIN = Depends(requiere_rol("admin"))
log = logging.getLogger("productos.consulta")


def get_cache(request: Request) -> CacheProductos:
    return request.app.state.cache


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
def consultar(producto_id: int, response: Response, db: Session = Depends(get_db),
              cache: CacheProductos = Depends(get_cache)):
    """Cache-aside: 1) Redis; 2) si no está (o Redis no responde), PostgreSQL y se guarda con TTL.
    Un 404 no se guarda en caché: un producto creado después nunca se vería como inexistente."""
    inicio = time.perf_counter()
    datos = cache.obtener(producto_id)
    resultado = HIT
    if datos is None:
        resultado = MISS
        datos = ProductoOut.model_validate(_o_404(db, producto_id)).model_dump()
        cache.guardar(producto_id, datos)
    response.headers["X-Cache"] = resultado
    log.info("consulta producto_id=%s cache=%s duracion_ms=%.2f", producto_id, resultado,
             (time.perf_counter() - inicio) * 1000)
    return datos


@router.post("/productos", response_model=ProductoOut, status_code=201, dependencies=[SOLO_ADMIN])
def crear(datos: ProductoIn, db: Session = Depends(get_db)):
    producto = Producto(**datos.model_dump())
    db.add(producto)
    db.commit()
    return producto


@router.put("/productos/{producto_id}", response_model=ProductoOut, dependencies=[SOLO_ADMIN])
def actualizar(producto_id: int, datos: ProductoUpdate, db: Session = Depends(get_db),
               cache: CacheProductos = Depends(get_cache)):
    producto = _o_404(db, producto_id)
    cambios = datos.model_dump(exclude_unset=True)
    if cambios:
        for campo, valor in cambios.items():
            setattr(producto, campo, valor)
        producto.version += 1
        db.commit()
        # DESPUÉS del commit: si se invalidara antes, una lectura concurrente podría volver a
        # cachear el valor viejo (aún no confirmado el nuevo) y quedaría así hasta el TTL.
        cache.invalidar(producto_id)
    return producto


@router.delete("/productos/{producto_id}", response_model=ProductoOut, dependencies=[SOLO_ADMIN])
def desactivar(producto_id: int, db: Session = Depends(get_db),
               cache: CacheProductos = Depends(get_cache)):
    producto = _o_404(db, producto_id)
    if producto.activo:
        producto.activo = False
        producto.version += 1
        db.commit()
        # DESPUÉS del commit: si se invalidara antes, una lectura concurrente podría volver a
        # cachear el valor viejo (aún no confirmado el nuevo) y quedaría así hasta el TTL.
        cache.invalidar(producto_id)
    return producto


@router.get("/productos/{producto_id}/cotizacion", response_model=CotizacionOut,
            dependencies=[Depends(usuario_actual)])
def cotizacion(producto_id: int, db: Session = Depends(get_db)):
    """Fuente de verdad para el monto del préstamo: SIEMPRE lee de PostgreSQL, nunca de Redis."""
    p = _o_404(db, producto_id)
    return CotizacionOut(producto_id=p.id, nombre=p.nombre, precio_cop=int(p.precio_cop),
                         version=p.version, activo=p.activo, consultado_en=datetime.now(timezone.utc))
