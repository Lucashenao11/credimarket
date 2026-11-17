"""Caché de productos en Redis (patrón cache-aside).

- Clave: productos:v1:{producto_id}. El "v1" versiona el FORMATO del valor: si cambia el esquema
  de ProductoOut, se sube a v2 y las claves viejas simplemente expiran, sin borrarlas a mano.
- Valor: el JSON de ProductoOut. TTL: settings.cache_ttl_segundos (300 s; justificación en
  docs/redis-desempeno.md).
- Redis es opcional para responder: cualquier error (caído, lento, credenciales) se registra y la
  petición sigue con PostgreSQL.
- Límite de tiempo TOTAL de 100 ms por operación. Los timeouts de socket de redis-py no cubren la
  resolución DNS: con el contenedor detenido, Docker borra el nombre "redis" y resolverlo tardaba ~3,4 s
  (medido). Por eso cada operación corre en un hilo del pool y la petición espera como máximo el límite;
  si vence, se responde desde PostgreSQL y el hilo termina solo en segundo plano.
- Tras un fallo, las LECTURAS y escrituras de relleno se saltan Redis durante unos segundos (pausa),
  para no pagar el timeout en cada petición mientras Redis está caído. La INVALIDACIÓN siempre se
  intenta: saltarla podría dejar un precio viejo en la caché.
- Invalidaciones pendientes: si un DELETE falla (Redis caído o inalcanzable), el id se anota y, cuando
  Redis vuelve, esas claves se borran ANTES de leer de la caché. Hace falta porque Redis guarda sus
  datos al apagarse y los recarga: sin esto, el precio viejo reaparecía hasta vencer el TTL (visto en la
  evidencia). La lista vive en memoria: si Productos se reinicia con pendientes, la cota es el TTL.
"""
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as LimiteVencido

import redis

log = logging.getLogger("productos.cache")

HIT, MISS = "HIT", "MISS"
# Pocos hilos: con Redis sano cada operación dura < 1 ms; con Redis caído la pausa evita acumularlas.
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="redis")


def clave(producto_id: int) -> str:
    return f"productos:v1:{producto_id}"


class CacheProductos:
    def __init__(self, cliente: "redis.Redis | None", ttl_segundos: int, pausa_tras_fallo_s: float = 5.0,
                 limite_s: float = 0.1):
        self.cliente = cliente
        self.ttl = ttl_segundos
        self.pausa = pausa_tras_fallo_s
        self.limite = limite_s
        self._pausado_hasta = 0.0
        self._pendientes: set[int] = set()  # ids cuya invalidación falló
        self._lock = threading.Lock()       # FastAPI atiende endpoints síncronos en varios hilos

    @classmethod
    def desde_url(cls, url: str, ttl_segundos: int, timeout_s: float, pausa_tras_fallo_s: float):
        if not url:
            log.warning("REDIS_URL vacío: la caché queda desactivada (todo se lee de PostgreSQL)")
            return cls(None, ttl_segundos, pausa_tras_fallo_s, limite_s=timeout_s)
        cliente = redis.Redis.from_url(url, socket_timeout=timeout_s, socket_connect_timeout=timeout_s,
                                       retry_on_timeout=False, decode_responses=True)
        return cls(cliente, ttl_segundos, pausa_tras_fallo_s, limite_s=timeout_s)

    def _ejecutar(self, fn, *args):
        """Ejecuta la operación con un límite de tiempo total (incluye DNS, conexión y respuesta)."""
        futuro = _POOL.submit(fn, *args)
        try:
            return futuro.result(timeout=self.limite)
        except LimiteVencido:
            raise redis.TimeoutError(f"sin respuesta en {self.limite * 1000:.0f} ms") from None

    # --- disponibilidad -------------------------------------------------------------------------
    def _disponible(self) -> bool:
        return self.cliente is not None and time.monotonic() >= self._pausado_hasta

    def _fallo(self, operacion: str, error: Exception) -> None:
        self._pausado_hasta = time.monotonic() + self.pausa
        log.warning("redis no disponible en %s (%s: %s); se usa PostgreSQL y se pausa la caché %.0f s",
                    operacion, type(error).__name__, error, self.pausa)

    def _vaciar_pendientes(self) -> bool:
        """Borra las claves cuya invalidación falló. True si no queda ninguna pendiente."""
        with self._lock:
            pendientes = list(self._pendientes)
        if not pendientes:
            return True
        try:
            self._ejecutar(self.cliente.delete, *[clave(p) for p in pendientes])
        except redis.RedisError as e:
            self._fallo("delete de pendientes", e)
            return False
        with self._lock:
            self._pendientes.difference_update(pendientes)
        log.info("invalidaciones pendientes aplicadas al volver Redis: %s", sorted(pendientes))
        return True

    @property
    def pendientes(self) -> set[int]:
        with self._lock:
            return set(self._pendientes)

    def ping(self) -> bool:
        if self.cliente is None:
            return False
        try:
            return bool(self._ejecutar(self.cliente.ping))
        except redis.RedisError:
            return False

    # --- operaciones ----------------------------------------------------------------------------
    def obtener(self, producto_id: int) -> dict | None:
        """El producto si está en caché; None si no está o si Redis no responde."""
        if not self._disponible() or not self._vaciar_pendientes():
            return None
        try:
            valor = self._ejecutar(self.cliente.get, clave(producto_id))
        except redis.RedisError as e:
            self._fallo("get", e)
            return None
        return json.loads(valor) if valor is not None else None

    def guardar(self, producto_id: int, datos: dict) -> None:
        if not self._disponible():
            return
        try:
            self._ejecutar(lambda: self.cliente.set(clave(producto_id), json.dumps(datos), ex=self.ttl))
        except redis.RedisError as e:
            self._fallo("set", e)

    def invalidar(self, producto_id: int) -> bool:
        """Borra la clave. Se llama DESPUÉS del commit. Devuelve False si Redis no respondió:
        en ese caso el valor viejo puede sobrevivir hasta que venza el TTL (cota de desactualización)."""
        if self.cliente is None:
            return True
        try:
            self._ejecutar(self.cliente.delete, clave(producto_id))
            return True
        except redis.RedisError as e:
            self._fallo("delete", e)
            with self._lock:
                self._pendientes.add(producto_id)
            log.error("no se pudo invalidar %s: queda pendiente y se borrará cuando Redis vuelva "
                      "(si Productos se reinicia antes, la cota es el TTL de %d s)", clave(producto_id), self.ttl)
            return False
