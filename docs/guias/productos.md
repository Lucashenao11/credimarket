# Productos — guía de lectura

**Estado: completo.** CRUD con versión que sube en cada cambio (precio, nombre, categoría o estado), desactivar
(borrado lógico) y reactivar (`PUT` con `"activo": true`), cotización y caché Redis. 5 productos de ejemplo
(ids 1..5 = existencias de Inventario). 19 pruebas (`docker compose exec productos pytest -q`).

**Contrato de cotización (no cambiar sin avisar a Lucas):**
`{producto_id, nombre, precio_cop, version, activo, consultado_en}`. Cualquier usuario autenticado puede consultarla
(Préstamos reenvía el token del usuario; no hay tokens de servicio). **Siempre lee PostgreSQL, nunca Redis.**

## Dónde está cada cosa

| Archivo | Qué hace |
|---|---|
| `app/routers/productos.py` | Endpoints. `consultar` aplica cache-aside y pone `X-Cache`; `actualizar` y `desactivar` invalidan **después** del commit; `cotizacion` no toca Redis |
| `app/cache.py` | `CacheProductos`: clave `productos:v1:{id}`, TTL, límite total de 100 ms por operación (incluye DNS), pausa de 5 s tras un fallo, invalidaciones pendientes que se aplican cuando Redis vuelve |
| `app/config.py` | `REDIS_URL`, `CACHE_TTL_SEGUNDOS` (300), `REDIS_TIMEOUT_SEGUNDOS` (0.1), `REDIS_PAUSA_TRAS_FALLO_SEGUNDOS` (5) |
| `app/main.py` | Crea la caché al iniciar; CORS con `expose_headers=["X-Cache"]`; `/health` informa el estado de Redis |
| `tests/test_cache.py` | 14 pruebas con `fakeredis`: hit/miss, TTL, invalidación (prueba 9), cotización sin caché, 404 no cacheado, Redis caído, pausa, pendientes, reactivar |

## Para explicar en la sustentación

- **Por qué invalidar después del commit:** si se borra antes, una lectura concurrente puede volver a cachear el valor viejo.
- **Por qué borrar y no escribir el valor nuevo:** la siguiente lectura rellena con lo que diga PostgreSQL; dos escrituras simultáneas no dejan en Redis algo distinto a la base.
- **Por qué la cotización no usa caché:** define el monto del préstamo; un precio viejo sería un préstamo mal calculado.
- **Qué pasa si Redis cae:** se responde desde PostgreSQL; la primera petición tarda ~100 ms y las siguientes no tocan Redis durante 5 s.
- **Cuándo puede verse un dato viejo y por cuánto:** ver `docs/redis-desempeno.md` §3 (cota: el TTL de 300 s, y solo en la vista de detalle).

Informe completo, mediciones y evidencia: [`docs/redis-desempeno.md`](../redis-desempeno.md).
