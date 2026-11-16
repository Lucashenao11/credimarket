# Productos — estado y pendientes del compañero

**Hecho (versión básica, sin Redis):** CRUD, desactivar (borrado lógico), versión que sube en cada cambio,
`GET /productos/{id}/cotizacion` (lee siempre de PostgreSQL), 5 productos de ejemplo (ids 1..5 = existencias de Inventario), 5 pruebas.

**Contrato de cotización (no cambiar sin avisar a Lucas):**
`{producto_id, nombre, precio_cop, version, activo, consultado_en}`. Cualquier usuario autenticado puede consultarla
(Préstamos reenvía el token del usuario; no hay tokens de servicio).

## Pendiente: Redis (cache-aside) — 10 % de la nota
Buscar `TODO(compañero)` en `app/`:
1. `config.py`: `redis_url`, `cache_ttl_segundos`. Agregar `redis` a `requirements.txt`.
2. `routers/productos.py::consultar`: leer Redis → si no está, leer la base y guardar con TTL (clave `productos:v1:{id}`).
3. `actualizar` y `desactivar`: invalidar la clave DESPUÉS del `commit`.
4. Si Redis falla: responder desde la base, con timeout corto (p. ej. 0.5 s) y sin romper la petición.
5. La **cotización NO usa caché** (es la fuente de verdad del monto).
6. Evidencia: prueba de hit/miss, invalidación, caída de Redis, y `docs/redis-desempeno.md` (clave, TTL, invalidación, cuándo hay datos viejos, mediciones con/sin caché).
