"""Pruebas de la caché (cache-aside con Redis) usando fakeredis.

Cubren: miss y luego hit, TTL, invalidación tras actualizar y desactivar (después del commit),
cotización que nunca usa la caché, 404 no cacheado y Redis caído sin error para el usuario.
"""
import fakeredis
import pytest

from app.cache import CacheProductos, clave
from app.main import app

NUEVO = {"nombre": "Portátil X", "categoria": "computadores", "precio_cop": 3_000_000}


def _crear(client) -> int:
    return client.post("/productos", json=NUEVO).json()["id"]


def test_primera_consulta_miss_y_luego_hit(client, redis_falso):
    pid = _crear(client)
    r1 = client.get(f"/productos/{pid}")
    r2 = client.get(f"/productos/{pid}")
    assert r1.headers["X-Cache"] == "MISS"
    assert r2.headers["X-Cache"] == "HIT"
    assert r1.json() == r2.json()
    assert redis_falso.exists(clave(pid))


def test_la_clave_tiene_ttl(client, redis_falso):
    pid = _crear(client)
    client.get(f"/productos/{pid}")
    assert 0 < redis_falso.ttl(clave(pid)) <= 300


def test_cambio_de_precio_invalida_y_la_siguiente_consulta_trae_el_nuevo(client, redis_falso):
    """Prueba 9: tras cambiar el precio, nunca se sirve el precio viejo desde la caché."""
    pid = _crear(client)
    client.get(f"/productos/{pid}")  # queda en caché con 3 000 000
    client.put(f"/productos/{pid}", json={"precio_cop": 3_500_000})
    assert not redis_falso.exists(clave(pid))
    r = client.get(f"/productos/{pid}")
    assert r.headers["X-Cache"] == "MISS"
    assert r.json()["precio_cop"] == 3_500_000 and r.json()["version"] == 2


def test_desactivar_invalida(client, redis_falso):
    pid = _crear(client)
    client.get(f"/productos/{pid}")
    client.delete(f"/productos/{pid}")
    r = client.get(f"/productos/{pid}")
    assert r.headers["X-Cache"] == "MISS" and r.json()["activo"] is False


def test_cotizacion_nunca_usa_la_cache(client, redis_falso):
    pid = _crear(client)
    # Un valor viejo "envenenado" en la caché no debe afectar la cotización
    redis_falso.set(clave(pid), '{"id": %d, "nombre": "viejo", "categoria": "x", "precio_cop": 1, '
                                '"version": 1, "activo": true}' % pid)
    c = client.get(f"/productos/{pid}/cotizacion")
    assert c.json()["precio_cop"] == 3_000_000
    assert "X-Cache" not in c.headers


def test_cotizacion_no_llena_la_cache(client, redis_falso):
    pid = _crear(client)
    client.get(f"/productos/{pid}/cotizacion")
    assert not redis_falso.exists(clave(pid))


def test_404_no_se_guarda_en_cache(client, redis_falso):
    assert client.get("/productos/999").status_code == 404
    assert not redis_falso.exists(clave(999))


@pytest.fixture
def redis_caido():
    servidor = fakeredis.FakeServer()
    servidor.connected = False  # toda operación lanza ConnectionError, como con Redis detenido
    return servidor


def test_redis_caido_responde_desde_postgres(client, redis_caido):
    app.state.cache = CacheProductos(fakeredis.FakeRedis(server=redis_caido, decode_responses=True),
                                     ttl_segundos=300)
    pid = _crear(client)
    r = client.get(f"/productos/{pid}")
    assert r.status_code == 200 and r.headers["X-Cache"] == "MISS"
    assert r.json()["nombre"] == "Portátil X"
    # Escribir también funciona: la invalidación falla en silencio para el usuario
    assert client.put(f"/productos/{pid}", json={"precio_cop": 3_100_000}).status_code == 200
    assert client.delete(f"/productos/{pid}").status_code == 200


def test_tras_un_fallo_se_pausa_y_luego_se_recupera(redis_caido):
    cache = CacheProductos(fakeredis.FakeRedis(server=redis_caido, decode_responses=True),
                           ttl_segundos=300, pausa_tras_fallo_s=60)
    assert cache.obtener(1) is None          # falla y activa la pausa
    redis_caido.connected = True
    cache.cliente.set(clave(1), '{"id": 1}')
    assert cache.obtener(1) is None          # en pausa: ni siquiera intenta Redis
    cache.pausa, cache._pausado_hasta = 0, 0  # vence la pausa
    assert cache.obtener(1) == {"id": 1}     # se recupera sin reiniciar el servicio


def test_invalidar_se_intenta_aunque_este_en_pausa(redis_caido):
    cache = CacheProductos(fakeredis.FakeRedis(server=redis_caido, decode_responses=True),
                           ttl_segundos=300, pausa_tras_fallo_s=60)
    cache.obtener(1)                         # pausa activa
    redis_caido.connected = True
    cache.cliente.set(clave(1), '{"id": 1}')
    assert cache.invalidar(1) is True        # la invalidación no respeta la pausa
    assert not cache.cliente.exists(clave(1))


def test_invalidacion_fallida_se_aplica_cuando_redis_vuelve(redis_caido):
    """Redis conserva sus datos al reiniciar: sin reintento, el precio viejo reaparecería hasta el TTL."""
    cache = CacheProductos(fakeredis.FakeRedis(server=redis_caido, decode_responses=True),
                           ttl_segundos=300, pausa_tras_fallo_s=0)
    redis_caido.connected = True
    cache.guardar(1, {"id": 1, "precio_cop": 100})       # valor en caché
    redis_caido.connected = False
    assert cache.invalidar(1) is False                    # el precio cambió con Redis caído
    assert cache.pendientes == {1}
    redis_caido.connected = True                          # Redis vuelve CON el valor viejo
    assert cache.cliente.exists(clave(1))
    assert cache.obtener(1) is None                       # primero borra la pendiente: no sirve el viejo
    assert not cache.cliente.exists(clave(1)) and cache.pendientes == set()


def test_mientras_haya_pendientes_sin_borrar_no_se_lee_la_cache(redis_caido):
    cache = CacheProductos(fakeredis.FakeRedis(server=redis_caido, decode_responses=True),
                           ttl_segundos=300, pausa_tras_fallo_s=0)
    redis_caido.connected = False
    cache.invalidar(1)
    assert cache.obtener(1) is None and cache.pendientes == {1}   # sigue caído: PostgreSQL
