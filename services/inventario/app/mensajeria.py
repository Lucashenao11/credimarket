"""Mensajería con RabbitMQ: outbox, inbox, publicador y consumidor.

ESTE ARCHIVO ES IDÉNTICO EN PRÉSTAMOS E INVENTARIO. Si cambias uno, cambia el otro.

Garantías (lee esto antes que el código):
  * Outbox:  el mensaje se escribe en la MISMA transacción que el cambio de negocio. Un hilo lo publica
             después, con confirmación del broker. Si el servicio cae, el mensaje sigue en la base.
  * Entrega "al menos una vez": puede publicarse o entregarse más de una vez (nunca se pierde).
  * Inbox:   cada mensaje trae un message_id; la tabla mensajes_procesados evita reprocesarlo.
  * Ack:     el consumidor confirma (ack) DESPUÉS de que el manejador terminó y confirmó su transacción.
  * Fallos:  se reintenta hasta MAX_REINTENTOS; después el mensaje va a la cola de mensajes muertos (DLQ).
"""
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone

import pika
from sqlalchemy import DateTime, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .db import Base, SessionLocal

log = logging.getLogger("mensajeria")

EXCHANGE = "credimarket"
DLX = "credimarket.dlx"
COLA_INVENTARIO = "inventario.comandos"
COLA_PRESTAMOS = "prestamos.eventos"
RUTAS = {
    COLA_INVENTARIO: ["reserva.solicitada", "reserva.liberar", "salida.confirmar"],
    COLA_PRESTAMOS: ["inventario.reservado", "inventario.insuficiente", "reserva.vencida",
                     "salida.confirmada"],
}
MAX_REINTENTOS = 3


def _ahora():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Tablas
# ---------------------------------------------------------------------------

class Outbox(Base):
    """Bandeja de salida: mensajes por publicar (publicado_en vacío) o ya publicados."""
    __tablename__ = "outbox"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)  # es el message_id
    routing_key: Mapped[str] = mapped_column(String(60), nullable=False)
    tipo: Mapped[str] = mapped_column(String(60), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora, index=True)
    publicado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MensajeProcesado(Base):
    """Bandeja de entrada: ids de mensajes ya procesados (la PRIMARY KEY es la deduplicación)."""
    __tablename__ = "mensajes_procesados"

    message_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tipo: Mapped[str] = mapped_column(String(60), nullable=False)
    procesado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)


def encolar(db: Session, routing_key: str, tipo: str, payload: dict,
            message_id: str | None = None) -> str:
    """Agrega un mensaje al outbox. NO hace commit: va en la transacción de quien lo llama."""
    message_id = message_id or str(uuid.uuid4())
    db.add(Outbox(id=message_id, routing_key=routing_key, tipo=tipo,
                  payload=json.dumps(payload, sort_keys=True)))
    return message_id


def ya_procesado(db: Session, message_id: str) -> bool:
    return db.get(MensajeProcesado, message_id) is not None


def marcar_procesado(db: Session, mensaje: dict) -> None:
    """Agrega el registro de 'visto'. NO hace commit. Si el id ya existe, el commit lanza IntegrityError."""
    db.add(MensajeProcesado(message_id=mensaje["message_id"], tipo=mensaje["tipo"]))


# ---------------------------------------------------------------------------
# Topología
# ---------------------------------------------------------------------------

def declarar_topologia(ch) -> None:
    ch.exchange_declare(EXCHANGE, exchange_type="direct", durable=True)
    ch.exchange_declare(DLX, exchange_type="direct", durable=True)
    for cola, rutas in RUTAS.items():
        ch.queue_declare(f"{cola}.dlq", durable=True)
        ch.queue_bind(f"{cola}.dlq", DLX, routing_key=cola)
        ch.queue_declare(cola, durable=True, arguments={
            "x-dead-letter-exchange": DLX, "x-dead-letter-routing-key": cola})
        for ruta in rutas:
            ch.queue_bind(cola, EXCHANGE, routing_key=ruta)


def _propiedades(message_id: str, tipo: str, reintentos: int):
    return pika.BasicProperties(delivery_mode=2, message_id=message_id, type=tipo,
                                content_type="application/json",
                                headers={"x-reintentos": reintentos})


# ---------------------------------------------------------------------------
# Publicador (lee el outbox)
# ---------------------------------------------------------------------------

class Publicador(threading.Thread):
    def __init__(self, url: str, detener: threading.Event):
        super().__init__(daemon=True, name="publicador-outbox")
        self.url, self.detener = url, detener

    def publicar_pendientes(self, ch, limite: int = 50) -> int:
        """Publica los mensajes pendientes de a uno; marca cada uno solo tras la confirmación del broker."""
        with SessionLocal() as db:
            filas = db.scalars(select(Outbox).where(Outbox.publicado_en.is_(None))
                               .order_by(Outbox.creado_en).limit(limite)).all()
            for fila in filas:
                cuerpo = json.dumps({"message_id": fila.id, "tipo": fila.tipo,
                                     "payload": json.loads(fila.payload)})
                ch.basic_publish(EXCHANGE, fila.routing_key, cuerpo.encode(),
                                 _propiedades(fila.id, fila.tipo, 0), mandatory=True)
                fila.publicado_en = _ahora()
                db.commit()
            return len(filas)

    def run(self):
        while not self.detener.is_set():
            try:
                conexion = pika.BlockingConnection(pika.URLParameters(self.url))
                ch = conexion.channel()
                ch.confirm_delivery()  # basic_publish espera la confirmación del broker
                declarar_topologia(ch)
                log.info("Publicador del outbox conectado")
                while not self.detener.is_set():
                    if self.publicar_pendientes(ch) == 0:
                        conexion.process_data_events(time_limit=1)
                conexion.close()
            except Exception:
                log.exception("Publicador: error; reintento en 3 s")
                self.detener.wait(3)


# ---------------------------------------------------------------------------
# Consumidor
# ---------------------------------------------------------------------------

class Consumidor(threading.Thread):
    """Llama a manejador(db, mensaje) por cada mensaje. El manejador hace su propio commit."""

    def __init__(self, url: str, cola: str, manejador, detener: threading.Event):
        super().__init__(daemon=True, name=f"consumidor-{cola}")
        self.url, self.cola, self.manejador, self.detener = url, cola, manejador, detener

    def al_recibir(self, ch, method, props, body: bytes) -> None:
        try:
            mensaje = json.loads(body)
        except ValueError:
            log.error("Mensaje ilegible; va a la cola de mensajes muertos")
            ch.basic_nack(method.delivery_tag, requeue=False)
            return
        try:
            with SessionLocal() as db:
                self.manejador(db, mensaje)
        except Exception:
            reintentos = int((props.headers or {}).get("x-reintentos", 0))
            log.exception("Falló el manejo de %s (reintento %s de %s)",
                          mensaje.get("tipo"), reintentos, MAX_REINTENTOS)
            if reintentos < MAX_REINTENTOS:
                time.sleep(min(2 * (reintentos + 1), 5))
                ch.basic_publish(EXCHANGE, method.routing_key, body,
                                 _propiedades(mensaje.get("message_id", ""), mensaje.get("tipo", ""),
                                              reintentos + 1))
                ch.basic_ack(method.delivery_tag)
            else:
                ch.basic_nack(method.delivery_tag, requeue=False)  # -> cola de mensajes muertos
            return
        ch.basic_ack(method.delivery_tag)  # SOLO después de que el manejador terminó y confirmó

    def run(self):
        while not self.detener.is_set():
            try:
                conexion = pika.BlockingConnection(pika.URLParameters(self.url))
                ch = conexion.channel()
                declarar_topologia(ch)
                ch.basic_qos(prefetch_count=1)
                ch.basic_consume(queue=self.cola, on_message_callback=self.al_recibir, auto_ack=False)
                log.info("Consumidor conectado a %s", self.cola)
                while not self.detener.is_set():
                    conexion.process_data_events(time_limit=1)
                conexion.close()
            except Exception:
                log.exception("Consumidor %s: error; reintento en 3 s", self.cola)
                self.detener.wait(3)
