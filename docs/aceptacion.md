# Pruebas de aceptación

Estado de cada prueba y cómo reproducirla. Todas suponen `docker compose up -d --build` y unos 15 s de espera.

| # | Qué comprueba | Cómo se ejecuta | Responsable |
|---|---|---|---|
| 1–7 | Idempotencia de solicitudes, máquina de estados, reserva atómica, eventos duplicados, tardíos y mensajes muertos | `scripts\demo-prestamos.ps1`, `scripts\demo-inventario.ps1`, `scripts\demo-flujo.ps1` y `pytest` en cada servicio | Lucas |
| 8 | Caché Redis: miss, hit, expiración, invalidación y caída de Redis (la API sigue respondiendo desde PostgreSQL) | `python scripts/evidencia_redis.py demo` (termina con `EVIDENCIA REDIS COMPLETA`) y `docker compose exec productos pytest -q`. Evidencia: `docs/evidencia/redis-demo.log`; mediciones con `... medir` | Juan David |
| 9 | Cambio de precio: tras `PUT /productos/{id}` la caché se invalida, la consulta trae el precio nuevo y la versión sube; la cotización nunca usa la caché | Paso 4 de `scripts/evidencia_redis.py demo` y `tests/test_cache.py::test_cambio_de_precio_invalida_y_la_siguiente_consulta_trae_el_nuevo` | Juan David |
| 10 | Modelo vs. API: la probabilidad del pipeline exportado y la de `POST /riesgo/predict` son iguales (incluye faltantes) | `ml\.venv\Scripts\python ml\scripts\prueba10.py` (Linux: `ml/.venv/bin/python …`). Debe terminar en `PRUEBA 10 SUPERADA`. Evidencia: `ml/evidencia/prueba10.log` | Juan David |
| 11 | Promoción y rollback: v1 → v2 → v1 cambiando solo `active.json`, verificado contra `/modelo/info` y `/riesgo/predict` | `ml\.venv\Scripts\python ml\scripts\prueba11.py`. Debe terminar en `PRUEBA 11 SUPERADA`. Evidencia: `ml/evidencia/prueba11.log` | Juan David |
| 12 | Importar dos veces el mismo CSV: 5 insertados + 3 errores; luego 5 ya existentes + 3 errores | `scripts\demo-clientes.ps1` | Lucas |
| 13 | Un cliente no ve ni modifica lo de otro; las operaciones de admin rechazan a clientes; sin token → 401 | `scripts\aceptacion-roles.ps1` (24 comprobaciones; termina con error si alguna falla) | Lucas |
| 14 | Frontend: cada rol ve solo sus pantallas; un cliente que escribe una ruta de admin vuelve al inicio | Manual (lista abajo) | Lucas |
| 15 | Frontend: solicitar dos veces con la misma clave no duplica; el botón se bloquea mientras envía | Manual (lista abajo) | Lucas |
| 16 | Frontend: estados de carga, vacío y error con reintento; sin respuestas simuladas | Manual (lista abajo) | Lucas |

## Lista manual para 14–16 (http://localhost:4200)

**14 · Roles**
1. Entra como `ana`: el menú muestra Catálogo, Solicitar, Mis solicitudes y Mi perfil. Escribe `/admin/clientes` en la barra: vuelve al inicio.
2. Cierra sesión y entra como `admin`: el menú muestra Préstamos, Inventario, Clientes y Modelo. Escribe `/solicitar`: vuelve al inicio.
3. Con la sesión de `ana` abierta, espera a que venza el token (o bórralo en DevTools → Application → Session Storage) y pulsa cualquier opción: llega al login con el aviso de sesión vencida.

**15 · Idempotencia en pantalla**
1. Como `ana`, solicita 1 unidad de un producto. Debe verse "Solicitud recibida", el estado `PENDIENTE INVENTARIO` y la aclaración de que **todavía no está aprobado**.
2. En DevTools → Network, activa "Offline", pulsa Enviar (error de conexión) y desactiva Offline. Pulsa Reintentar: la clave de idempotencia mostrada es la **misma** y solo se crea una solicitud (revísalo en "Mis solicitudes").
3. Cambia la cantidad: la clave cambia (es otra solicitud).
4. Pulsa Enviar muchas veces rápido: el botón queda deshabilitado mientras hay un envío en curso.

**16 · Estados de la interfaz**
1. Detén Préstamos (`docker compose stop prestamos`) y abre "Mis solicitudes": aparece un mensaje de conexión con botón **Reintentar**. Vuelve a arrancarlo (`docker compose start prestamos`), pulsa Reintentar y carga.
2. Entra como `beto` sin solicitudes: se ve el estado vacío con el enlace a "Haz la primera".
3. Formularios: deja vacío el producto o pon cantidad 9: aparecen mensajes junto al campo y no se envía nada.
4. Solicita como `ana` y observa que la lista se refresca sola cada 3 s hasta salir de `PENDIENTE INVENTARIO`.

## Preparación para 8–11

- **8 y 9** solo necesitan Python 3 (biblioteca estándar) y el compose arriba.
- **10 y 11** necesitan el entorno de ML (Python **3.11**, las mismas versiones que Préstamos):
  ```powershell
  py -3.11 -m venv ml\.venv
  ml\.venv\Scripts\pip install -r ml\requirements.txt
  ```
  En Linux/Mac: `python3.11 -m venv ml/.venv && ml/.venv/bin/pip install -r ml/requirements.txt`.
- Préstamos lee `ml/registry/active.json` **solo al arrancar**. Después de un `git pull` que cambie el registro, o antes de la prueba 10:
  `docker compose restart prestamos` y comprobar la versión en la pantalla Modelo o en `GET /modelo/info`.
- La prueba 11 reinicia Préstamos dos veces (≈ 1 min) y deja `active.json` en la versión inicial, con la promoción y el rollback añadidos a su `historial`.
- `evidencia_redis.py demo` recrea Productos con TTL de 8 s para mostrar la expiración y al final lo deja en 300 s. Ambos modos crean productos "Evidencia Redis …" y los desactivan al terminar.
