# Guía de demostración

Recorrido para ejecutar el flujo completo desde el navegador y las pruebas de aceptación. Duración aproximada: 20 minutos.

## 0. Preparación

> Las existencias de la tabla del punto 4 son las iniciales. Cada caso las consume. Para repetir la demostración desde cero: `docker compose down -v` y `docker compose up -d --build` (el `-v` borra los datos).

1. Desde un clon limpio: `.\scripts\setup.ps1` y `docker compose up -d --build` (Linux/Mac: `./scripts/setup.sh`). Espera unos 20 segundos.
2. Abre **http://localhost:4200**.
3. Cuentas de prueba (las contraseñas están en tu `.env`: `DEMO_ADMIN_PASSWORD` para el administrador y `DEMO_CLIENTE_PASSWORD` para los clientes):

| Usuario | Rol | Perfil |
|---|---|---|
| `admin` | administrador | Ve y opera Préstamos, Inventario, Clientes, Modelo y administra el Catálogo |
| `ana` | cliente (`CLI-DEMO-0001`) | Perfil de **bajo riesgo**: el modelo suele dar decisión favorable |
| `beto` | cliente (`CLI-DEMO-0002`) | Perfil de **alto riesgo**: el modelo suele rechazar |

4. Existencias iniciales: producto 1 (portátil Lenovo) 10 unidades; **producto 2 (portátil gamer) 1 unidad**; **producto 3 (celular) 0 unidades**; producto 4 (tablet) 5; producto 5 (monitor) 3.
5. **Tiempo de la reserva.** `RESERVA_TTL_SEGUNDOS` vale 60 en `.env.example`: una solicitud aprobada que no se entrega en 60 s se cancela sola con motivo `RESERVA_VENCIDA`. Para una demostración tranquila pon `RESERVA_TTL_SEGUNDOS=600` en `.env` y ejecuta `docker compose up -d inventario`. Para mostrar el vencimiento, déjalo en 60.

## 1. Flujo desde el navegador

Cada caso indica la **evidencia** que se debe señalar en pantalla.

| # | Caso | Pasos | Evidencia |
|---|---|---|---|
| 1 | **Préstamo aprobado** (prueba 1) | Entra como `ana` → Solicitar → producto 1, cantidad 1, plazo 12 → Enviar | Aparece "Solicitud recibida" en `PENDIENTE INVENTARIO` con la aclaración de que aún no está aprobado. En **Mis solicitudes** pasa sola a `APROBADA` (se refresca cada 3 s). Como admin, en Inventario el producto 1 muestra disponible 9 y reservado 1 |
| 2 | **Rechazo por riesgo** (prueba 2) | Entra como `beto` → solicita producto 1 | Estado `RECHAZADA` al instante, motivo "Riesgo de incumplimiento por encima del umbral". En el historial queda la decisión; en Inventario **no** hay reserva nueva. El admin ve en Préstamos la probabilidad (columna Riesgo) y la versión del modelo que decidió (columna Modelo) |
| 3 | **Falta de inventario** (prueba 3) | Como `ana`, solicita el producto 3 (sin existencias) | Pasa a `CANCELADA SIN STOCK`. Inventario sigue en 0 (nunca negativo) |
| 4 | **Cancelación con reserva liberada** (prueba 7) | Como `ana`, solicita el producto 4 y, cuando esté `APROBADA`, pulsa **Cancelar solicitud** | Estado `CANCELADA`. Como admin, Inventario devuelve la unidad (disponible 5, reservado 0) y Movimientos registra la liberación |
| 5 | **Entrega** (prueba 1) | Como `ana`, solicita el producto 5 y espera `APROBADA`. Como `admin` → Préstamos → **Entregar** | El préstamo pasa a `COMPLETADA`. En Inventario la unidad sale de bodega (disponible 2, reservado 0) y Movimientos muestra la salida |
| 6 | **Dos solicitudes por la última unidad** (prueba 4) | Ejecuta `.\scripts\demo-flujo.ps1` (sección 2, con su propio producto de 1 unidad) o `.\scripts\demo-inventario.ps1` (10 solicitudes simultáneas) | Una sola `APROBADA` y el resto `CANCELADA SIN STOCK`; reservado = 1. Refresca Inventario en el navegador |
| 7 | **Actualización de un precio** (prueba 9) | Como `admin` → Catálogo → edita el precio del producto 1 → Guardar. Luego, como `ana`, solicita el producto 1 | La versión del producto sube. La nueva solicitud muestra el monto con el precio nuevo y la versión de cotización usada |
| 8 | **Importación de clientes** (prueba 12) | Como `admin` → Clientes → Importar CSV → elige `scripts/datos/clientes_demo.csv` → Importar. Repite con el mismo archivo | Primera vez: 5 insertadas, 0 ya existían, 3 con error (con fila y motivo). Segunda vez: 0 insertadas, 5 ya existían, 3 con error. No se duplica ningún cliente |
| 9 | **Versión del modelo** (prueba 10) | Como `admin` → Modelo | Versión activa, run de MLflow, umbral, métricas, variables e historial de promociones. En Préstamos, cada decisión guarda la versión que la tomó |
| 10 | **Formulario inválido, sesión vencida, API caída** (prueba 16) | Cantidad 9 o producto vacío; `docker compose stop prestamos` y abrir Mis solicitudes; borrar el token en DevTools | Mensajes claros, botón Reintentar y vuelta al login con aviso; nunca un éxito simulado |

## 2. Pruebas con scripts y registros

Se complementan con la interfaz, como pide el enunciado. Todas con el compose arriba.

| Prueba | Comando | Qué se muestra |
|---|---|---|
| 1, 3, 4, 7 | `.\scripts\demo-flujo.ps1` | Flujo normal, última unidad, cancelación, entrega y evento tardío en vivo (se detiene Inventario, vence el tiempo de espera y vuelve) |
| 5 | `.\scripts\demo-prestamos.ps1` | Misma petición repetida → un solo préstamo (200 con `Idempotent-Replay`); misma clave con otro cuerpo → 409 |
| 4, 5, 7 | `.\scripts\demo-inventario.ps1` | 10 reservas simultáneas por la última unidad (gana una); el mismo mensaje 3 veces (una sola reserva); la cancelación repetida (la unidad vuelve una vez); vencimiento de la reserva |
| 6 | Pruebas `test_mensajeria.py` de Inventario y Préstamos (`docker compose exec <servicio> pytest -q`) | Reintentos (hasta 3) y envío a la cola de mensajes muertos; verlas en RabbitMQ, colas `*.dlq` |
| 6 | `docker compose stop rabbitmq` → solicitar → `docker compose start rabbitmq` | La solicitud confirmada no se pierde: el outbox la publica al volver el broker |
| 8 | `python scripts/evidencia_redis.py demo` | Miss, hit, expiración, invalidación y caída de Redis |
| 8 | `docker compose stop redis` y consultar un producto | Sigue respondiendo desde PostgreSQL |
| 10 | `ml\.venv\Scripts\python ml\scripts\prueba10.py` | Probabilidad del modelo exportado = la de `POST /riesgo/predict` |
| 11 | `ml\.venv\Scripts\python ml\scripts\prueba11.py` | Promoción v1 → v2 y rollback, con trazabilidad en `active.json` |
| 12 | `.\scripts\demo-clientes.ps1` | CSV dos veces sin duplicar |
| 13 | `.\scripts\aceptacion-roles.ps1` | Un cliente no accede a préstamos ajenos (404), operaciones de admin rechazadas (403), sin token (401) |
| Unitarias | `docker compose exec <servicio> pytest -q` | Clientes, Productos, Inventario y Préstamos |

Preparación del entorno de ML para las pruebas 10 y 11: ver [aceptacion.md](aceptacion.md#preparación-para-811).

## 3. Herramientas para señalar durante la demo

- **RabbitMQ:** http://localhost:15672 (usuario `credimarket`, contraseña `RABBITMQ_PASSWORD` del `.env`): colas, mensajes y colas de mensajes muertos.
- **MLflow:** http://localhost:5000: ejecuciones de los candidatos, parámetros, métricas y artefactos.
- **Documentación de cada API:** puertos 8001 a 8004, ruta `/docs`.
- **Consumo de recursos con Redis:** `docker stats`.

## 4. Orden sugerido para el tiempo de la sustentación

1. Arquitectura en 3 minutos: [arquitectura.md](arquitectura.md) (diagrama general, secuencia y máquina de estados).
2. Casos 1, 2, 3 y 5 desde el navegador.
3. Una prueba de fallos: `demo-flujo.ps1` (evento tardío) o el corte de RabbitMQ.
4. Redis: `evidencia_redis.py demo` y el informe de desempeño.
5. Modelo: pantalla Modelo, prueba 10 y prueba 11.
6. Dejar de reserva los casos 6 a 10 para lo que pida el profesor.
