import json
from datetime import timedelta

from sqlalchemy import func, select

from app.consumidor import manejar_comando
from app.mensajeria import MensajeProcesado, Outbox
from app.models import Existencia, Reserva
from app.reservas import ahora_utc, reservar
from app.vencimiento import emitir_vencidas
from app.reservas import vencer_reservas


def _msg(tipo, prestamo_id, message_id, **extra):
    return {"message_id": message_id, "tipo": tipo, "payload": {"prestamo_id": prestamo_id, **extra}}


def _reservar_msg(prestamo_id, message_id, producto_id=1, cantidad=2):
    return _msg("ReservaSolicitada", prestamo_id, message_id, producto_id=producto_id, cantidad=cantidad)


def _salidas(db):
    db.expire_all()
    return [(f.tipo, json.loads(f.payload)["prestamo_id"]) for f in db.scalars(select(Outbox).order_by(Outbox.creado_en))]


def _stock(db, pid):
    e = db.get(Existencia, pid, populate_existing=True)
    return (e.disponible, e.reservado)


def test_reserva_solicitada_responde_reservado(bodega):
    assert manejar_comando(bodega, _reservar_msg("P-1", "m-1")) == "RESERVADA"
    assert _stock(bodega, 1) == (3, 2)
    assert _salidas(bodega) == [("InventarioReservado", "P-1")]


def test_sin_stock_responde_insuficiente(bodega):
    assert manejar_comando(bodega, _reservar_msg("P-1", "m-1", cantidad=9)) == "INSUFICIENTE"
    assert _stock(bodega, 1) == (5, 0)
    assert _salidas(bodega) == [("InventarioInsuficiente", "P-1")]


def test_el_mismo_mensaje_dos_veces_no_reserva_dos_veces(bodega):
    """Prueba de aceptación 5 (por el broker): mensaje repetido, un solo efecto y una sola respuesta."""
    manejar_comando(bodega, _reservar_msg("P-1", "m-1"))
    assert manejar_comando(bodega, _reservar_msg("P-1", "m-1")) == "DUPLICADO"
    assert _stock(bodega, 1) == (3, 2)
    assert len(_salidas(bodega)) == 1
    assert bodega.scalar(select(func.count()).select_from(MensajeProcesado)) == 1


def test_otro_mensaje_para_el_mismo_prestamo_tampoco_descuenta(bodega):
    """Otro message_id, mismo préstamo: lo frena la UNIQUE de la reserva, no el inbox."""
    manejar_comando(bodega, _reservar_msg("P-1", "m-1"))
    assert manejar_comando(bodega, _reservar_msg("P-1", "m-2")) == "YA_PROCESADA"
    assert _stock(bodega, 1) == (3, 2)


def test_reentrega_tras_caida_entre_reservar_y_responder(bodega):
    """Inventario alcanzó a reservar (commit) pero cayó antes de encolar la respuesta."""
    reservar(bodega, "P-1", 1, 2)
    assert manejar_comando(bodega, _reservar_msg("P-1", "m-1")) == "YA_PROCESADA"
    assert _stock(bodega, 1) == (3, 2)
    assert _salidas(bodega) == [("InventarioReservado", "P-1")]  # la respuesta que faltaba


def test_no_responde_reservado_si_la_reserva_ya_no_esta_activa(bodega):
    manejar_comando(bodega, _reservar_msg("P-1", "m-1"))
    manejar_comando(bodega, _msg("LiberarReserva", "P-1", "m-2"))
    assert manejar_comando(bodega, _reservar_msg("P-1", "m-3")) == "YA_PROCESADA"
    assert [t for t, _ in _salidas(bodega)] == ["InventarioReservado"]  # ninguna respuesta nueva


def test_liberar_reserva_dos_veces(bodega):
    manejar_comando(bodega, _reservar_msg("P-1", "m-1"))
    assert manejar_comando(bodega, _msg("LiberarReserva", "P-1", "m-2")) == "LIBERADA"
    assert manejar_comando(bodega, _msg("LiberarReserva", "P-1", "m-3")) == "YA_FINALIZADA"
    assert _stock(bodega, 1) == (5, 0)


def test_liberar_una_reserva_que_nunca_existio_no_rompe(bodega):
    assert manejar_comando(bodega, _msg("LiberarReserva", "P-X", "m-1")) == "NO_EXISTE"


def test_confirmar_salida_responde_salida_confirmada(bodega):
    manejar_comando(bodega, _reservar_msg("P-1", "m-1"))
    assert manejar_comando(bodega, _msg("ConfirmarSalida", "P-1", "m-2")) == "CONFIRMADA"
    assert _salidas(bodega)[-1] == ("SalidaConfirmada", "P-1")
    assert _stock(bodega, 1) == (3, 0)


def test_reentrega_de_confirmar_salida_tras_caida_igual_avisa(bodega):
    from app.reservas import confirmar_salida
    reservar(bodega, "P-1", 1, 2)
    confirmar_salida(bodega, "P-1")  # alcanzó a confirmar, cayó antes de encolar
    assert manejar_comando(bodega, _msg("ConfirmarSalida", "P-1", "m-9")) == "YA_FINALIZADA"
    assert _salidas(bodega) == [("SalidaConfirmada", "P-1")]


def test_reserva_vencida_emite_un_solo_aviso(bodega):
    reservar(bodega, "P-1", 1, 2)
    vencer_reservas(bodega, ahora=ahora_utc() + timedelta(hours=1))
    assert emitir_vencidas(bodega) == ["P-1"]
    assert emitir_vencidas(bodega) == []  # el segundo ciclo no vuelve a avisar
    assert _salidas(bodega) == [("ReservaVencida", "P-1")]
    assert bodega.scalar(select(Reserva.estado)) == "VENCIDA"
