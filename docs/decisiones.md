# Decisiones de arquitectura — CrediMarket

Formato: decisión, alternativas consideradas, por qué, qué se sacrifica.

## D1 — Broker: RabbitMQ

**Decisión:** RabbitMQ transporta los comandos y eventos entre Préstamos e Inventario.

**Alternativas:** Kafka en modo KRaft con un nodo.

**Por qué:**
- El patrón es de comandos (ReservaSolicitada, LiberarReserva, ConfirmarSalida) hacia un único consumidor, con eventos de respuesta hacia Préstamos: es el caso de uso típico de una cola de trabajo.
- Reintentos limitados y cola de mensajes muertos (dead-letter exchange) nativos; con Kafka hay que programarlos.
- Publisher confirms y acks manuales encajan con el outbox (marcar como publicado solo tras la confirmación) y con el consumidor idempotente (ack después del commit).
- Menos memoria y menos configuración que Kafka para un equipo de una persona.

**Qué se sacrifica:** el replay de eventos desde el broker. El historial durable vive en las bases de cada servicio (outbox y tablas de mensajes procesados).

## D2 — Tecnología de los servicios

**Decisión:** los cuatro servicios en FastAPI síncrono, SQLAlchemy y Pydantic. Los consumidores de RabbitMQ y los publicadores del outbox corren como hilos dentro del mismo contenedor de cada servicio.

**Alternativas:** FastAPI asíncrono (asyncpg, aio-pika); consumidores y publicadores en un segundo contenedor por servicio.

**Por qué:** una sola plantilla de proyecto que se repite en los cuatro servicios, sobre el stack que mejor domino. Los hilos dentro del mismo contenedor evitan cualquier discusión sobre un "quinto servicio".

**Qué se sacrifica:** la API y el consumidor de un servicio escalan y se reinician juntos, y un fallo grave del proceso afecta a ambos.

## D3 — Base de datos

**Decisión:** una instancia de PostgreSQL con cuatro bases de datos (productos, clientes, prestamos, inventario), cada una con su propio usuario, sin permiso de conexión a las bases de los demás. MLflow usa una quinta base en la misma instancia.

**Alternativas:** una sola base con cuatro esquemas y permisos por esquema; cuatro instancias de PostgreSQL.

**Por qué:** el aislamiento se demuestra fácilmente (el usuario de Préstamos no puede ni conectarse a la base de Inventario) y una sola instancia consume poco.

**Qué se sacrifica:** la instancia es un punto único de falla; si se cae, se caen los cuatro servicios.

## D4 — Frontend: Angular

**Decisión:** Angular.

**Alternativas:** React con Vite.

**Por qué:** es el framework que conozco y puedo defender cualquier parte en la sustentación.

**Qué se sacrifica:** más archivos de configuración y un arranque un poco más pesado.

## D5 — Tokens de prueba: JWT RS256

**Decisión:** Clientes es el único que tiene la llave privada y emite los tokens de prueba (solo con el modo demo activo). Productos, Préstamos e Inventario validan con la llave pública. Roles: cliente, administrador y servicio (para llamadas entre servicios, por ejemplo Préstamos → Clientes).

**Alternativas:** JWT HS256 con un secreto compartido por variable de entorno.

**Por qué:** con HS256, cualquier servicio que tenga el secreto podría emitir tokens; con RS256 solo Clientes puede emitirlos y los demás solo pueden verificarlos.

**Qué se sacrifica:** manejar un par de llaves en lugar de un solo secreto.

## D6 — Tiempos de espera (configurables por variable de entorno)

**Decisión:**
- Vencimiento de la reserva: 30 minutos por defecto; 60 segundos en el modo demo. Al vencer, Inventario libera las unidades y publica ReservaVencida; Préstamos pasa a CANCELADA con motivo RESERVA_VENCIDA.
- Timeout de PENDIENTE_INVENTARIO: 60 segundos. Si Inventario no responde, Préstamos pasa a CANCELADA con motivo TIMEOUT_INVENTARIO.
- Evento tardío: si llega InventarioReservado para un préstamo ya cancelado, Préstamos no lo reactiva y publica LiberarReserva para devolver las unidades.

**Alternativas:** tiempos realistas (24 horas para la reserva, 5 minutos para el timeout); un estado nuevo VENCIDA.

**Por qué:** los tiempos cortos permiten demostrar el vencimiento y el evento tardío en vivo. Usar CANCELADA con motivo respeta los estados mínimos del enunciado.

**Qué se sacrifica:** los valores por defecto no reflejan un negocio real; en producción se ajustarían por configuración.

## D7 — Promoción del modelo

**Decisión:** cada versión exportada vive en `ml/registry/<model_version>/` con su pipeline y su manifiesto. El archivo `ml/registry/active.json` indica la versión activa. Un script promueve una versión candidata o hace rollback cambiando ese archivo; Préstamos lo lee al iniciar.

**Alternativas:** alias `champion` en el registro de modelos de MLflow.

**Por qué:** Préstamos arranca sin depender de que MLflow esté disponible, y la versión activa es explícita y trazable.

**Qué se sacrifica:** el script de promoción hay que construirlo y mantenerlo; no se aprovecha el registro de modelos de MLflow.

## D8 — Secretos

**Decisión:** ningún secreto vive en el repositorio. El script `scripts/setup.ps1` (o `scripts/setup.sh` en Linux/Mac) genera, la primera vez, el archivo `.env` con contraseñas aleatorias y el par de llaves RSA en `secrets/`. Ambos están en `.gitignore`; el repositorio solo incluye `.env.example`. Arranque desde un clon limpio: ejecutar el script y luego `docker compose up`.

**Alternativas:** un contenedor de arranque dentro del compose que genere las llaves y contraseñas en un volumen.

**Por qué:** es simple de explicar y de mantener; el contenedor de arranque costaba 2–3 horas más y obligaba a configurar PostgreSQL y RabbitMQ para leer contraseñas desde archivos.

**Qué se sacrifica:** levantar el sistema requiere un comando adicional antes de `docker compose up`.
