from sqlalchemy import select

from app import eventos
from app.models import HistorialEstado
from tests.conftest import nuevo_prestamo


def _estado(db, p):
    db.refresh(p)
    return p.estado


def test_reserva_confirmada_aprueba(db):
    p = nuevo_prestamo(db)
    assert eventos.reserva_confirmada(db, p.id) == "APROBADA"
    assert _estado(db, p) == "APROBADA"


def test_mensaje_repetido_de_reserva_confirmada_es_duplicado(db):
    p = nuevo_prestamo(db)
    eventos.reserva_confirmada(db, p.id)
    assert eventos.reserva_confirmada(db, p.id) == "DUPLICADO"
    assert len(db.scalars(select(HistorialEstado)).all()) == 1


def test_evento_tardio_no_reactiva_un_prestamo_cancelado(db):
    p = nuevo_prestamo(db, "CANCELADA")
    assert eventos.reserva_confirmada(db, p.id) == "LIBERAR_RESERVA"
    assert _estado(db, p) == "CANCELADA"


def test_evento_tardio_tras_timeout(db):
    p = nuevo_prestamo(db)
    assert eventos.timeout_inventario(db, p.id) == "CANCELADA"
    assert eventos.reserva_confirmada(db, p.id) == "LIBERAR_RESERVA"
    assert _estado(db, p) == "CANCELADA" and p.motivo == "TIMEOUT_INVENTARIO"


def test_inventario_insuficiente(db):
    p = nuevo_prestamo(db)
    assert eventos.inventario_insuficiente(db, p.id) == "CANCELADA_SIN_STOCK"
    assert _estado(db, p) == "CANCELADA_SIN_STOCK"
    assert eventos.inventario_insuficiente(db, p.id) == "IGNORADO"


def test_reserva_vencida_de_un_prestamo_aprobado(db):
    p = nuevo_prestamo(db, "APROBADA")
    assert eventos.reserva_vencida(db, p.id) == "CANCELADA"
    assert _estado(db, p) == "CANCELADA" and p.motivo == "RESERVA_VENCIDA"


def test_entrega(db):
    p = nuevo_prestamo(db, "APROBADA")
    assert eventos.salida_confirmada(db, p.id) == "COMPLETADA"
    assert eventos.salida_confirmada(db, p.id) == "IGNORADO"
