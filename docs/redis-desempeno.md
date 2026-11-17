# Caché Redis en Productos — diseño, evidencia y desempeño

Autor: Juan David Sepúlveda Londoño. Mediciones del 16 de noviembre de 2026.
Código: `services/productos/app/cache.py` y `services/productos/app/routers/productos.py`.
Evidencia: `scripts/evidencia_redis.py` y `docs/evidencia/`.

## 1. Resumen

| | |
|---|---|
| **Patrón** | Cache-aside en `GET /productos/{id}` |
| **Clave / TTL** | `productos:v1:{id}` / 300 s |
| **Invalidación** | `DELETE` de la clave después del `commit` en `PUT` y `DELETE /productos/{id}` |
| **Cotización** | **Nunca** usa la caché: siempre lee PostgreSQL |
| **Redis caído** | Respuesta desde PostgreSQL. Cuesta 100 ms la primera petición y nada las siguientes durante la pausa |
| **Latencia en el servidor (p50)** | HIT 0,09 ms frente a MISS 0,60 ms |
| **Latencia en el cliente (p50 / p95)** | HIT 0,93 / 1,08 ms frente a MISS 1,56 / 1,74 ms |
| **Tasa de aciertos** | 98,6 % en una carga mixta con cambios de precio |

## 2. Diseño

### 2.1 Qué se cachea y qué no

| Endpoint | ¿Caché? | Por qué |
|---|---|---|
| `GET /productos/{id}` | **Sí** | Es la lectura más frecuente: la pantalla de detalle y el catálogo. El valor cambia poco, solo cuando un administrador lo edita |
| `GET /productos/{id}/cotizacion` | **Nunca** | Es la fuente de verdad del precio con el que Préstamos calcula el monto (contrato 4.2). Un precio viejo ahí sería un préstamo mal calculado |
| `GET /productos` (listado) | No | Depende del filtro `solo_activos` y cambia con cualquier producto. Invalidarlo bien obligaría a borrar todas las variantes en cada escritura, y el ahorro sería pequeño |
| Producto inexistente (404) | No | Si se guardara el "no existe", un producto creado después aparecería como inexistente hasta que venciera el TTL |

### 2.2 Clave, valor y TTL

- **Clave `productos:v1:{id}`.** El prefijo separa este uso de cualquier otro en el mismo Redis. El `v1` versiona el **formato** del valor: si cambia el esquema de `ProductoOut`, se pasa a `v2` y las claves viejas vencen solas, sin borrarlas a mano ni leer valores con el formato anterior.
- **Valor:** el JSON de `ProductoOut` (`id`, `nombre`, `categoria`, `precio_cop`, `version` y `activo`).
- **TTL de 300 s**, configurable con `CACHE_TTL_SEGUNDOS`. El TTL **no** es el mecanismo normal de frescura: de eso se encarga la invalidación. El TTL es la **cota máxima** de desactualización cuando la invalidación se pierde (ver §3). Lo elegí con estos criterios:
  - Los precios cambian pocas veces al día y solo los cambia un administrador. Un TTL más corto, por ejemplo 30 s, haría que los productos populares fallaran 10 veces más, sin ganar frescura en el caso normal.
  - En el peor caso, que un cliente vea en la pantalla de detalle un precio de hace hasta 5 minutos, el monto del préstamo no cambia, porque sale de la cotización.
  - Un TTL más largo, como 1 hora, ampliaría ese peor caso sin una ganancia que valga la pena: con 300 s la tasa de aciertos ya es del 98,6 %.

### 2.3 Lectura (cache-aside)

```
GET /productos/{id}
  1. Redis GET productos:v1:{id}
     ├─ está        → responder (X-Cache: HIT)
     └─ no está / Redis no responde
          2. PostgreSQL SELECT (404 si no existe: no se guarda)
          3. Redis SET productos:v1:{id} <json> EX 300
          4. responder (X-Cache: MISS)
  + una línea de log: "consulta producto_id=… cache=HIT|MISS duracion_ms=…"
```

### 2.4 Escritura e invalidación

`PUT` y `DELETE` hacen el `commit` en PostgreSQL y **después** el `DELETE` de la clave en Redis. Si se invalidara antes del `commit`, una lectura concurrente podría encontrar la clave vacía, leer de PostgreSQL el valor **viejo** (el nuevo aún no estaría confirmado) y volver a guardarlo. Ese valor viejo quedaría en la caché hasta que venciera el TTL.

Se borra la clave en vez de escribir el valor nuevo: la siguiente lectura la vuelve a llenar con lo que haya en PostgreSQL. Así no hay que replicar en Redis la lógica de la escritura, y dos escrituras simultáneas no pueden dejar en Redis un valor distinto al de la base.

### 2.5 Fallas de Redis

| Mecanismo | Qué hace | Por qué |
|---|---|---|
| **Límite total de 100 ms** por operación | Cada operación de Redis corre en un hilo, y la petición la espera como máximo 100 ms. Si se vence, se lee PostgreSQL | **Hallazgo de la evidencia:** los timeouts de socket de redis-py no cubren la resolución DNS. Al detener el contenedor, Docker borra el nombre `redis` y resolverlo tardaba **3,4 s** (medido). Con el límite total, la primera petición tras la caída tarda **103 ms** |
| **Pausa de 5 s** tras un fallo | Las lecturas y los rellenos se saltan Redis durante 5 s | Sin la pausa, con Redis caído cada petición pagaría los 100 ms. Con ella, solo una petición cada 5 s los paga (≈ 1,7 ms en la siguiente, medido) |
| **La invalidación ignora la pausa** | El `DELETE` siempre se intenta | Saltarse una invalidación es justo lo que deja un precio viejo en la caché |
| **Invalidaciones pendientes** | Si un `DELETE` falla, el id se anota y, cuando Redis vuelve, esas claves se borran **antes** de cualquier lectura de la caché | **Hallazgo de la evidencia:** Redis guarda sus datos en disco al apagarse y los recarga al arrancar. Sin este mecanismo, tras la caída se sirvió **HIT con el precio viejo** (1 250 000 cuando la base ya tenía 1 300 000) |
| **Ningún error llega al usuario** | Cualquier `RedisError` se registra (WARNING o ERROR) y la petición sigue | Redis es una optimización, no una dependencia para responder |

Estado visible:
- `GET /health` informa `"redis": "ok" | "no disponible"`, solo como información: Productos sigue respondiendo en ambos casos.
- La cabecera `X-Cache` está en `expose_headers` del CORS. Sin eso, el navegador la oculta al frontend, porque CORS solo expone por defecto las cabeceras simples.

## 3. Cuándo puede haber un dato desactualizado

| Escenario | ¿Puede verse un dato viejo? | Cota | Mitigación |
|---|---|---|---|
| Cambio normal por la API con Redis sano | No | — | Invalidación después del `commit` |
| Cambio con Redis caído o inalcanzable, y Redis vuelve | No, si Productos no se reinició | — | Invalidaciones pendientes, aplicadas antes de leer |
| Igual al anterior, pero Productos **se reinicia** antes de que vuelva Redis | Sí | ≤ TTL (300 s) | La lista de pendientes vive en memoria. En producción: Redis sin persistencia para la caché (`--save ""`) o una cola durable de invalidaciones |
| Carrera lectura/escritura: una lectura con MISS lee la fila vieja justo antes del `commit` y la guarda justo después del `DELETE` | Sí, en una ventana de microsegundos | ≤ TTL | Aceptado: es el límite conocido del cache-aside. Se podría reducir con un segundo `DELETE` diferido o guardando solo si la `version` no retrocede |
| Cambio hecho directamente en PostgreSQL (SQL manual, migración) | Sí | ≤ TTL | Cualquier cambio de datos debe pasar por la API. Si no, se borran las claves `productos:v1:*` |
| **Cotización** (monto del préstamo) | **Nunca** | — | No usa la caché, por diseño y con prueba automática |

Lo que puede quedar desactualizado como máximo es la **vista de detalle** del catálogo, y solo hasta el TTL. El dinero del préstamo nunca depende de la caché.

## 4. Evidencia funcional

`python scripts/evidencia_redis.py demo` (salida en [`evidencia/redis-demo.log`](evidencia/redis-demo.log)). El script recrea Productos con TTL de 8 s para mostrar la expiración en vivo; es el mismo código con otra configuración, y al final se restaura el TTL de 300 s. Usa un producto de prueba propio que desactiva al terminar.

| Paso | Lo que se observa | Resultado |
|---|---|---|
| 1. MISS | La clave no existe → `X-Cache: MISS` → la clave existe con TTL 8 | OK |
| 2. HIT | `X-Cache: HIT`, mismo cuerpo | OK |
| 3. Expiración | Tras 9 s, la clave ya no existe → `MISS` | OK |
| 4. Invalidación (prueba 9) | HIT → `PUT precio_cop=1250000` → la clave no existe → `MISS` con el precio nuevo y versión 2; la cotización también da 1 250 000 | OK |
| 5. Caída (`docker compose stop redis`) | `200 MISS` en 103 ms, luego 1,7 ms (pausa); `PUT` responde 200; `/health` dice `redis: no disponible` | OK |
| 6. Recuperación (`docker compose start redis`) | Redis recarga la clave con el precio viejo; Productos aplica la invalidación pendiente → `MISS` con 1 300 000 → `HIT` | OK |

También quedan las líneas de log de cada consulta y los avisos, por ejemplo:
```
INFO productos.consulta: consulta producto_id=8 cache=HIT duracion_ms=0.13
WARNING productos.cache: redis no disponible en get (TimeoutError: sin respuesta en 100 ms); se usa PostgreSQL y se pausa la caché 5 s
ERROR productos.cache: no se pudo invalidar productos:v1:8: queda pendiente y se borrará cuando Redis vuelva (...)
INFO productos.cache: invalidaciones pendientes aplicadas al volver Redis: [8]
```

## 5. Mediciones

`python scripts/evidencia_redis.py medir` (salida en [`evidencia/redis-mediciones.json`](evidencia/redis-mediciones.json) y `.log`).

Condiciones de la medición:
- Docker local, una conexión HTTP persistente, token de administrador.
- 1 000 peticiones por escenario, después de un calentamiento.
- Para el escenario "sin caché" se borra la clave **antes** de cada petición, fuera del tiempo medido, así que todas son MISS: es el camino que seguiría cada petición sin caché, más el `SET` de relleno.
- La cotización sirve de referencia, porque lee solo PostgreSQL sin tocar Redis.

### 5.1 Latencia vista por el cliente

| Escenario | p50 (ms) | p95 (ms) | p99 (ms) | Media (ms) |
|---|---|---|---|---|
| **Con caché (HIT)** | **0,93** | **1,08** | 1,19 | 0,94 |
| Sin caché (MISS forzado) | 1,56 | 1,74 | 1,94 | 1,59 |
| Cotización (solo PostgreSQL) | 1,23 | 1,38 | 1,45 | 1,25 |

### 5.2 Latencia dentro del servidor (`duracion_ms` del log)

Mide la lectura de Redis o PostgreSQL más la serialización, sin HTTP ni validación del JWT.

| Resultado | n | p50 (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|---|
| **HIT** | 3 021 | **0,09** | **0,12** | 0,19 |
| MISS | 1 030 | 0,60 | 0,72 | 0,93 |

### 5.3 Tasa de aciertos y recursos

La carga mixta fueron 2 000 lecturas sobre 10 productos con popularidad desigual (Zipf), con un cambio de precio cada 100 lecturas. Resultado: **1 971 HIT y 29 MISS, es decir 98,6 % de aciertos**. Coincide con los contadores de Redis (`keyspace_hits` 1 971, `keyspace_misses` 29). Los 29 MISS son los 10 primeros accesos, más las relecturas tras los 20 cambios de precio, menos los productos que no se volvieron a leer.

`docker stats` durante la carga mixta:

| Contenedor | CPU | Memoria |
|---|---|---|
| productos | 63,7 % | 74 MiB |
| **postgres** | **0,5 %** | 58 MiB |
| redis | 3,5 % | 8,7 MiB (`used_memory` 1,13 MB) |

### 5.4 Análisis

- **Dentro del servidor, un HIT es 6,7 veces más rápido que un MISS** (0,09 frente a 0,60 ms en p50). Desde el cliente la mejora es de 40 % en p50 y 38 % en p95, porque HTTP y la validación del JWT cuestan alrededor de 0,85 ms en ambos casos, y ese costo la caché no lo toca.
- Los valores absolutos son pequeños porque todo corre en la misma máquina, la tabla es diminuta y PostgreSQL la tiene en memoria. Con PostgreSQL en otra máquina, o bajo carga de las escrituras de Préstamos e Inventario, el MISS crece y el HIT no.
- **El beneficio principal es descargar PostgreSQL:** con 98,6 % de aciertos, solo 1,4 de cada 100 lecturas de detalle llegan a la base, que usó 0,5 % de CPU durante la carga. El cuello de botella pasa a ser el propio servicio (63,7 % de CPU en HTTP, JWT y serialización), que es más fácil de escalar horizontalmente que la base.
- **Costo del MISS frente a no tener caché:** el MISS forzado (1,56 ms) cuesta alrededor de 0,33 ms más que la cotización (1,23 ms), que es lo mismo sin Redis. Eso es lo que suman el `GET` fallido y el `SET` de relleno. Con 98,6 % de aciertos, el costo promedio queda muy por debajo del de no tener caché.
- **El costo en recursos es bajo:** Redis usa 8,7 MiB de memoria y alrededor de 1 KB por producto.

## 6. Pruebas automáticas

`docker compose exec productos pytest -q` (17 pruebas: las 5 originales y 12 de la caché con `fakeredis`, en `tests/test_cache.py`):
- primera consulta MISS y luego HIT; la clave tiene TTL;
- un cambio de precio invalida, y la siguiente lectura trae el precio nuevo (prueba 9); desactivar también invalida;
- la cotización ignora un valor "envenenado" en la caché y no la llena;
- un 404 no se guarda en caché;
- con Redis caído, `GET`, `PUT` y `DELETE` responden 200;
- tras un fallo hay pausa y luego recuperación sin reiniciar el servicio; la invalidación se intenta aunque haya pausa;
- una invalidación fallida se aplica cuando Redis vuelve, y mientras siga pendiente no se lee la caché.

## 7. Qué cambiaría en producción

- Redis dedicado a caché, **sin persistencia** (`--save ""`, `--appendonly no`) y con `--maxmemory` más `allkeys-lru`. Se pierde la caché al reiniciar Redis, pero no reaparecen valores viejos.
- Invalidaciones pendientes en una cola durable, o eventos de "producto cambiado" por RabbitMQ, si hubiera varias instancias de Productos y además fuera inaceptable la cota del TTL.
- Métricas de aciertos y latencia en un sistema de monitoreo, en vez de líneas de log.
- `docker-compose.yml` hace que Productos espere a que Redis esté sano **al arrancar** (`depends_on: service_healthy`). Una vez arriba, Productos tolera la caída de Redis, como muestra la evidencia. En producción se quitaría esa dependencia de arranque.
