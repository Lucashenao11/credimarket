# Pruebas de aceptación

Estado de cada prueba y cómo reproducirla. Todas suponen `docker compose up -d --build` y unos 15 s de espera.

| # | Qué comprueba | Cómo se ejecuta | Responsable |
|---|---|---|---|
| 1–7 | Idempotencia de solicitudes, máquina de estados, reserva atómica, eventos duplicados, tardíos y mensajes muertos | `scripts\demo-prestamos.ps1`, `scripts\demo-inventario.ps1`, `scripts\demo-flujo.ps1` y `pytest` en cada servicio | Lucas |
| 8–11 | Caché Redis (hit, miss, invalidación, caída), cambio de precio, modelo vs. API, promoción y rollback | Scripts y evidencia de Juan David (`ml/`, `scripts/`, informe de Redis) | Juan David |
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
