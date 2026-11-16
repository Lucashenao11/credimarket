"""Publicador, consumidor e inbox con un canal falso (no hace falta RabbitMQ)."""
import json
import threading

import pytest
from sqlalchemy import select

from app import mensajeria as m
from app.mensajeria import Consumidor, Outbox, Publicador, encolar


class CanalFalso:
    def __init__(self, falla_en_publicar=False):
        self.publicados, self.acks, self.nacks = [], [], []
        self.falla = falla_en_publicar

    def basic_publish(self, exchange, routing_key, body, properties, mandatory=False):
        if self.falla:
            raise RuntimeError("el broker no confirmó")
        self.publicados.append((routing_key, json.loads(body), properties.headers))

    def basic_ack(self, tag):
        self.acks.append(tag)

    def basic_nack(self, tag, requeue):
        self.nacks.append((tag, requeue))


class Metodo:
    delivery_tag, routing_key = 7, "inventario.reservado"


class Props:
    def __init__(self, reintentos=0):
        self.headers = {"x-reintentos": reintentos}


def _mensaje(tipo="ReservaSolicitada", prestamo_id="X", message_id="m-1"):
    return json.dumps({"message_id": message_id, "tipo": tipo, "payload": {"prestamo_id": prestamo_id}}).encode()


# ---------------- publicador ----------------

def test_publica_pendientes_y_los_marca(db):
    encolar(db, "reserva.solicitada", "ReservaSolicitada", {"prestamo_id": "P1"})
    db.commit()
    canal = CanalFalso()
    assert Publicador("x", threading.Event()).publicar_pendientes(canal) == 1
    ruta, cuerpo, _ = canal.publicados[0]
    assert ruta == "reserva.solicitada" and cuerpo["tipo"] == "ReservaSolicitada"
    assert cuerpo["message_id"] and cuerpo["payload"] == {"prestamo_id": "P1"}
    db.expire_all()
    assert db.scalars(select(Outbox)).one().publicado_en is not None
    assert Publicador("x", threading.Event()).publicar_pendientes(canal) == 0  # ya no hay pendientes


def test_si_el_broker_no_confirma_el_mensaje_sigue_pendiente(db):
    encolar(db, "reserva.solicitada", "ReservaSolicitada", {"prestamo_id": "P1"})
    db.commit()
    with pytest.raises(RuntimeError):
        Publicador("x", threading.Event()).publicar_pendientes(CanalFalso(falla_en_publicar=True))
    db.expire_all()
    assert db.scalars(select(Outbox)).one().publicado_en is None  # se reintentará: nunca se pierde


# ---------------- consumidor ----------------

def test_ack_solo_despues_de_manejar(db):
    orden = []
    c = Consumidor("x", "cola", lambda db, msg: orden.append("manejado"), threading.Event())
    canal = CanalFalso()
    canal.basic_ack = lambda tag: orden.append("ack")
    c.al_recibir(canal, Metodo, Props(), _mensaje())
    assert orden == ["manejado", "ack"]


def test_error_reintenta_republicando_con_contador(db, monkeypatch):
    monkeypatch.setattr(m.time, "sleep", lambda s: None)
    def falla(db, msg): raise RuntimeError("boom")
    canal = CanalFalso()
    Consumidor("x", "cola", falla, threading.Event()).al_recibir(canal, Metodo, Props(0), _mensaje())
    assert canal.publicados[0][2]["x-reintentos"] == 1 and canal.acks == [7] and canal.nacks == []


def test_tras_los_reintentos_va_a_la_cola_de_mensajes_muertos(db, monkeypatch):
    monkeypatch.setattr(m.time, "sleep", lambda s: None)
    def falla(db, msg): raise RuntimeError("boom")
    canal = CanalFalso()
    Consumidor("x", "cola", falla, threading.Event()).al_recibir(
        canal, Metodo, Props(m.MAX_REINTENTOS), _mensaje())
    assert canal.nacks == [(7, False)] and canal.acks == [] and canal.publicados == []


def test_mensaje_ilegible_va_directo_a_la_cola_de_mensajes_muertos(db):
    canal = CanalFalso()
    Consumidor("x", "cola", lambda d, msg: None, threading.Event()).al_recibir(canal, Metodo, Props(), b"{no es json")
    assert canal.nacks == [(7, False)]


