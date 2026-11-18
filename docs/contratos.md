# Contratos de la API y de los mensajes

Referencia de lo que cada servicio expone. La versión ejecutable y siempre al día está en la documentación automática de cada servicio (`/docs`): Productos 8001, Clientes 8002, Préstamos 8003, Inventario 8004.

**Autenticación.** Todas las rutas (salvo `/health`, `/ready` y `/auth/login`) exigen `Authorization: Bearer <token>`. El token es un JWT RS256 emitido solo por Clientes (claims `sub`, `rol`, `cliente_id`, `iss=credimarket-clientes`, `aud=credimarket`, `exp`). Los demás servicios solo verifican la firma con la llave pública. Roles: `cliente` y `admin`.
**Errores comunes:** 401 sin token, vencido o manipulado; 403 rol sin permiso; 404 recurso inexistente (o ajeno, para préstamos); 409 conflicto de estado; 422 cuerpo inválido.

## Clientes (puerto 8002)

| Método y ruta | Rol | Qué hace |
|---|---|---|
| `POST /auth/login` | público | Cuerpo `{usuario, password}` → `{access_token, token_type}`. 401 si las credenciales fallan |
| `GET /auth/me` | autenticado | Datos del token |
| `POST /clientes` | admin | Crea un cliente (`cliente_id` con formato `CLI-…`, datos financieros validados). 201 |
| `GET /clientes?limit&offset` | admin | Lista paginada |
| `GET /clientes/{id}` | admin o el propio cliente | Consulta. Un cliente que pide otro → 403 |
| `PATCH /clientes/{id}` | admin o el propio cliente | Actualización parcial. Un cliente solo puede editar su nombre y su correo (otro campo → 403); campos desconocidos → 422 |
| `POST /clientes/importar` | admin | Sube un CSV (`archivo`). Respuesta: `{archivo, total_filas, insertados, ya_existian, errores, filas[{fila, cliente_id, resultado, detalle}]}`. La clave externa es `cliente_id`: repetir el archivo no duplica |

Datos financieros del cliente: `ingresos_mensuales_cop` (>0), `obligaciones_mensuales_cop` (≥0), `tipo_empleo` (dependiente, independiente, temporal o vacío), `antiguedad_laboral_meses`, `meses_historial_crediticio`, `creditos_previos`, `atrasos_previos_30d`, `porcentaje_pago_puntual` (0–100 o vacío).

## Productos (puerto 8001)

| Método y ruta | Rol | Qué hace |
|---|---|---|
| `GET /productos?solo_activos=true` | autenticado | Lista |
| `GET /productos/{id}` | autenticado | Detalle. **Cache-aside** (Redis, TTL 300 s); cabecera `X-Cache: HIT` o `MISS` |
| `POST /productos` | admin | Crea `{nombre, categoria, precio_cop}`. 201 |
| `PUT /productos/{id}` | admin | Actualiza (incluye `activo`). Solo sube `version` si algo cambia realmente; invalida la caché después del commit |
| `DELETE /productos/{id}` | admin | Desactiva (no borra). Sube `version` e invalida la caché |
| `GET /productos/{id}/cotizacion` | autenticado | `{producto_id, nombre, precio_cop, version, activo, consultado_en}`. **Lee siempre de PostgreSQL, nunca de la caché**: es la fuente de verdad del monto |

## Préstamos (puerto 8003)

| Método y ruta | Rol | Qué hace |
|---|---|---|
| `POST /prestamos` | cliente | Inicia la solicitud. Encabezado **obligatorio** `Idempotency-Key` (≥ 8 caracteres). Cuerpo `{producto_id, cantidad (1–5), plazo_meses (6, 12, 18, 24 o 36)}`; cualquier otro campo (monto, precio, cliente_id) → 422 |
| `GET /prestamos?limit` | autenticado | Cliente: solo los suyos. Admin: todos |
| `GET /prestamos/{id}` | autenticado | Estado y decisión. Un préstamo ajeno → 404 |
| `GET /prestamos/{id}/historial` | autenticado | Transiciones de estado con motivo y hora |
| `POST /prestamos/{id}/cancelar` | dueño o admin | Cancela y libera la reserva. 409 si ya no se puede |
| `POST /prestamos/{id}/entregar` | admin | Solicita la entrega; Inventario confirma la salida y el préstamo pasa a COMPLETADA. 202; 409 si no está APROBADA |
| `GET /modelo/info` | autenticado | `model_version, run_id, umbral, features, clase_positiva, metricas, dataset_sha256, promovido_en, historial` |
| `POST /riesgo/predict` | admin | Prueba el pipeline con las 11 variables. Devuelve `{probabilidad_incumplimiento, umbral, decision (RIESGO_ALTO o FAVORABLE), model_version}`. No reserva inventario |
| `GET /health` | público | El proceso responde |
| `GET /ready` | público | `{ready, database, modelo}`; 503 si el modelo o la base no están listos |

**Códigos de `POST /prestamos`:**

| Código | Situación |
|---|---|
| 202 | Riesgo favorable: queda `PENDIENTE_INVENTARIO` esperando a Inventario |
| 201 | Decisión final inmediata: `RECHAZADA` (riesgo alto o regla de negocio) |
| 200 | Repetición de la misma petición (misma clave y mismo cuerpo): devuelve el préstamo original con `Idempotent-Replay: true` |
| 409 | La misma clave con un cuerpo distinto |
| 400 | Falta `Idempotency-Key` |
| 403 | El usuario no es cliente |
| 503 | Clientes, Productos o el modelo no disponibles |

La idempotencia se apoya en la restricción única `(cliente_id, clave)` y en el SHA-256 del cuerpo canónico. El monto sale de la cotización vigente, nunca del cliente.

**Estados:** ver [arquitectura.md](arquitectura.md#3-máquina-de-estados-del-préstamo). Motivos: `RIESGO_ALTO`, `CLIENTE_INACTIVO`, `INFORMACION_INSUFICIENTE`, `MONTO_FUERA_DE_RANGO`, `SIN_STOCK`, `TIMEOUT_INVENTARIO`, `RESERVA_VENCIDA`, `CANCELADO_POR_USUARIO`.

## Inventario (puerto 8004) — todo solo para admin

| Método y ruta | Qué hace |
|---|---|
| `GET /existencias` · `GET /existencias/{producto_id}` | `{producto_id, disponible, reservado, actualizado_en}` |
| `POST /existencias/{producto_id}/entradas` | `{cantidad}` (1–100 000). Suma al disponible y registra el movimiento |
| `GET /reservas?estado&limit` | `{prestamo_id, producto_id, cantidad, estado, motivo, vence_en, creada_en}` |
| `GET /movimientos?producto_id&limit` | `{producto_id, tipo, cantidad, prestamo_id, creado_en}` |
| `POST /reservas/{prestamo_id}/confirmar-salida` | Operación de apoyo por HTTP; el flujo normal usa el mensaje `ConfirmarSalida` |

La reserva es atómica: un `UPDATE … WHERE disponible >= cantidad` y una restricción que impide stock negativo; hay una reserva única por préstamo.

## Mensajes (RabbitMQ)

Sobre común, en JSON: `{"message_id": "<uuid>", "tipo": "<Tipo>", "payload": {…}}`. Intercambio `credimarket` (direct) con las llaves de la tabla; mensajes muertos en `credimarket.dlx`.

| Tipo | Llave | Lo publica | Lo consume | Payload |
|---|---|---|---|---|
| ReservaSolicitada | `reserva.solicitada` | Préstamos | Inventario | `prestamo_id, producto_id, cantidad` |
| LiberarReserva | `reserva.liberar` | Préstamos | Inventario | `prestamo_id, motivo` |
| ConfirmarSalida | `salida.confirmar` | Préstamos | Inventario | `prestamo_id` |
| InventarioReservado | `inventario.reservado` | Inventario | Préstamos | `prestamo_id` |
| InventarioInsuficiente | `inventario.insuficiente` | Inventario | Préstamos | `prestamo_id` |
| ReservaVencida | `reserva.vencida` | Inventario | Préstamos | `prestamo_id` |
| SalidaConfirmada | `salida.confirmada` | Inventario | Préstamos | `prestamo_id` |

Colas: `inventario.comandos` y `prestamos.eventos`, cada una con su `.dlq`. Garantías (outbox, entrega al menos una vez, inbox por `message_id`, ack después del commit, 3 reintentos y cola de mensajes muertos) en [mensajeria.md](mensajeria.md).

## Contrato del modelo (Préstamos ↔ ML)

- Carga al iniciar desde `ml/registry/active.json` → `ml/registry/<versión>/` (`pipeline.joblib`, `manifest.json`, ejemplos de entrada y salida).
- Se verifica el SHA-256 del artefacto contra el manifiesto; si no coincide, el servicio **no** arranca con ese modelo (`/ready` responde 503).
- Entrada: 11 variables, en el orden y con los nombres del manifiesto; clase positiva = 1 (incumplimiento a 90 días).
- La decisión de riesgo (probabilidad ≥ umbral → `RIESGO_ALTO`) **no** es la aprobación final: el préstamo solo queda APROBADO cuando Inventario confirma la reserva.
- Dependencias fijas: scikit-learn 1.5.2, pandas 2.2.3, numpy 2.1.3, joblib 1.4.2.
