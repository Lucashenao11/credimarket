import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import eventos
from app.mensajeria import Outbox
from app.timeouts import cancelar_pendientes_vencidos
from tests.conftest import USUARIO, nuevo_prestamo

CUERPO = {"producto_id": 1, "cantidad": 2, "plazo_meses": 12}


def _post(client, cuerpo=CUERPO, clave="clave-0001"):
    return client.post("/prestamos", json=cuerpo, headers={"Idempotency-Key": clave})


def _outbox(db):
    db.expire_all()
    return db.scalars(select(Outbox).order_by(Outbox.creado_en)).all()


def test_solicitud_favorable_deja_reserva_solicitada_en_el_outbox(client, db):
    p = _post(client).json()
    filas = _outbox(db)
    assert len(filas) == 1 and filas[0].routing_key == "reserva.solicitada"
    assert filas[0].tipo == "ReservaSolicitada" and filas[0].publicado_en is None
    assert json.loads(filas[0].payload) == {"prestamo_id": p["id"], "producto_id": 1, "cantidad": 2}


def test_solicitud_rechazada_no_pide_inventario(client, db, modelo):
    modelo.probabilidad = 0.9
    assert _post(client).json()["estado"] == "RECHAZADA"
    assert _outbox(db) == []


def test_repetir_la_solicitud_no_duplica_el_mensaje(client, db):
    _post(client)
    _post(client)
    assert len(_outbox(db)) == 1


def test_evento_tardio_pide_liberar_la_reserva(db):
    p = nuevo_prestamo(db, "CANCELADA")
    assert eventos.reserva_confirmada(db, p.id) == "LIBERAR_RESERVA"
    fila = _outbox(db)[0]
    assert fila.tipo == "LiberarReserva" and json.loads(fila.payload)["prestamo_id"] == p.id


def test_aprobar_no_genera_mensajes(db):
    p = nuevo_prestamo(db)
    eventos.reserva_confirmada(db, p.id)
    assert _outbox(db) == []


def test_timeout_cancela_y_encola_liberacion_juntos(db):
    p = nuevo_prestamo(db)
    assert eventos.timeout_inventario(db, p.id) == "CANCELADA"
    assert [f.tipo for f in _outbox(db)] == ["LiberarReserva"]


def test_timeout_de_un_prestamo_ya_aprobado_no_hace_nada(db):
    p = nuevo_prestamo(db, "APROBADA")
    assert eventos.timeout_inventario(db, p.id) == "IGNORADO"
    assert _outbox(db) == []


def test_el_hilo_de_timeouts_solo_cancela_los_pendientes_viejos(db):
    viejo, nuevo = nuevo_prestamo(db), nuevo_prestamo(db)
    viejo.creado_en = datetime.now(timezone.utc) - timedelta(seconds=120)
    db.commit()
    assert cancelar_pendientes_vencidos(db) == [viejo.id]
    db.refresh(nuevo)
    assert nuevo.estado == "PENDIENTE_INVENTARIO"


def test_cancelar_por_el_cliente(client, db):
    p = nuevo_prestamo(db)
    r = client.post(f"/prestamos/{p.id}/cancelar")
    assert r.status_code == 200 and r.json()["estado"] == "CANCELADA"
    assert r.json()["motivo"] == "CANCELADO_POR_USUARIO"
    assert [f.tipo for f in _outbox(db)] == ["LiberarReserva"]
    assert client.post(f"/prestamos/{p.id}/cancelar").status_code == 409  # ya es final


def test_no_se_cancela_un_prestamo_ajeno(client, db):
    p = nuevo_prestamo(db, cliente_id="CLI-2")
    assert client.post(f"/prestamos/{p.id}/cancelar").status_code == 404


def test_entrega_solo_admin_y_solo_aprobado(client, db):
    p = nuevo_prestamo(db, "APROBADA")
    assert client.post(f"/prestamos/{p.id}/entregar").status_code == 403
    USUARIO["rol"] = "admin"
    assert client.post(f"/prestamos/{p.id}/entregar").status_code == 202
    assert [f.tipo for f in _outbox(db)] == ["ConfirmarSalida"]
    pendiente = nuevo_prestamo(db)
    assert client.post(f"/prestamos/{pendiente.id}/entregar").status_code == 409
