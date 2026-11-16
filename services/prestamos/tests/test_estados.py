import pytest
from sqlalchemy import select

from app import estados as e
from app.models import HistorialEstado
from tests.conftest import nuevo_prestamo

PERMITIDAS = [
    (e.PENDIENTE_INVENTARIO, e.APROBADA), (e.PENDIENTE_INVENTARIO, e.CANCELADA_SIN_STOCK),
    (e.PENDIENTE_INVENTARIO, e.CANCELADA), (e.APROBADA, e.COMPLETADA), (e.APROBADA, e.CANCELADA),
]
PROHIBIDAS = [
    (e.PENDIENTE_INVENTARIO, e.COMPLETADA), (e.PENDIENTE_INVENTARIO, e.RECHAZADA),
    (e.APROBADA, e.CANCELADA_SIN_STOCK), (e.APROBADA, e.PENDIENTE_INVENTARIO),
    (e.RECHAZADA, e.CANCELADA), (e.RECHAZADA, e.APROBADA),
    (e.CANCELADA_SIN_STOCK, e.CANCELADA), (e.CANCELADA, e.PENDIENTE_INVENTARIO),
    (e.CANCELADA, e.APROBADA), (e.COMPLETADA, e.CANCELADA),
]


@pytest.mark.parametrize("desde,hacia", PERMITIDAS)
def test_transicion_permitida(db, desde, hacia):
    p = nuevo_prestamo(db, desde)
    assert e.cambiar_estado(db, p.id, desde, hacia, "X") is True
    db.commit()
    db.refresh(p)
    assert p.estado == hacia and p.motivo == "X"


@pytest.mark.parametrize("desde,hacia", PROHIBIDAS)
def test_transicion_prohibida(db, desde, hacia):
    p = nuevo_prestamo(db, desde)
    with pytest.raises(e.TransicionInvalida):
        e.cambiar_estado(db, p.id, desde, hacia)
    db.refresh(p)
    assert p.estado == desde


@pytest.mark.parametrize("final", [e.RECHAZADA, e.CANCELADA_SIN_STOCK, e.COMPLETADA, e.CANCELADA])
def test_estados_finales_no_tienen_salida(final):
    assert e.TRANSICIONES[final] == set()


def test_si_el_estado_ya_cambio_devuelve_false_y_no_toca_nada(db):
    p = nuevo_prestamo(db, e.CANCELADA)
    # alguien cree que sigue PENDIENTE y quiere aprobarlo (evento tardío)
    assert e.cambiar_estado(db, p.id, e.PENDIENTE_INVENTARIO, e.APROBADA) is False
    db.commit()
    db.refresh(p)
    assert p.estado == e.CANCELADA
    assert db.scalars(select(HistorialEstado)).all() == []


def test_cada_cambio_deja_historial(db):
    p = nuevo_prestamo(db)
    e.cambiar_estado(db, p.id, e.PENDIENTE_INVENTARIO, e.CANCELADA, "TIMEOUT_INVENTARIO")
    db.commit()
    fila = db.scalars(select(HistorialEstado)).one()
    assert (fila.estado_anterior, fila.estado_nuevo, fila.motivo) == (
        e.PENDIENTE_INVENTARIO, e.CANCELADA, "TIMEOUT_INVENTARIO")
