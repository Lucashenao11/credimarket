from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import reservas as logica
from ..db import get_db
from ..models import Existencia, Movimiento, Reserva
from ..schemas import (EntradaIn, ExistenciaOut, MovimientoOut, ReservaOut,
                       ResultadoOperacion)
from ..security import requiere_rol

# Todas las operaciones de Inventario son administrativas: el cliente nunca habla con Inventario.
router = APIRouter(tags=["inventario"], dependencies=[Depends(requiere_rol("admin"))])


@router.get("/existencias", response_model=list[ExistenciaOut])
def listar_existencias(db: Session = Depends(get_db)):
    return db.scalars(select(Existencia).order_by(Existencia.producto_id)).all()


@router.get("/existencias/{producto_id}", response_model=ExistenciaOut)
def consultar_existencia(producto_id: int, db: Session = Depends(get_db)):
    existencia = db.get(Existencia, producto_id)
    if existencia is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Producto sin existencias registradas")
    return existencia


@router.post("/existencias/{producto_id}/entradas", response_model=ExistenciaOut)
def registrar_entrada(producto_id: int, entrada: EntradaIn, db: Session = Depends(get_db)):
    return logica.registrar_entrada(db, producto_id, entrada.cantidad)


@router.get("/reservas", response_model=list[ReservaOut])
def listar_reservas(estado: str | None = None, limit: int = Query(100, ge=1, le=500),
                    db: Session = Depends(get_db)):
    consulta = select(Reserva).order_by(Reserva.id.desc()).limit(limit)
    if estado:
        consulta = consulta.where(Reserva.estado == estado)
    return db.scalars(consulta).all()


@router.get("/movimientos", response_model=list[MovimientoOut])
def listar_movimientos(producto_id: int | None = None, limit: int = Query(100, ge=1, le=500),
                       db: Session = Depends(get_db)):
    consulta = select(Movimiento).order_by(Movimiento.id.desc()).limit(limit)
    if producto_id:
        consulta = consulta.where(Movimiento.producto_id == producto_id)
    return db.scalars(consulta).all()


@router.post("/reservas/{prestamo_id}/confirmar-salida", response_model=ResultadoOperacion)
def confirmar_salida(prestamo_id: str, db: Session = Depends(get_db)):
    """Entrega simulada directa (administrador). El flujo normal usa POST /prestamos/{id}/entregar en Préstamos."""
    return ResultadoOperacion(prestamo_id=prestamo_id,
                              resultado=logica.confirmar_salida(db, prestamo_id))
