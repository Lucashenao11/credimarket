# CrediMarket

Venta de productos tecnológicos a crédito: cuatro microservicios (Productos, Clientes, Préstamos e Inventario), frontend web, RabbitMQ, Redis, PostgreSQL y un modelo de riesgo con su ciclo MLOps en MLflow.

> Datos y operaciones de crédito ficticios. Se evalúa ingeniería de software y MLOps.

## Integrantes

| Integrante | Responsabilidades |
|---|---|
| Lucas | Clientes, Préstamos, Inventario, RabbitMQ (outbox e idempotencia), esqueleto del frontend y sus pantallas, documentación |
| Juan David Sepúlveda Londoño ([@Huanda98GG](https://github.com/Huanda98GG)) | Productos y Redis, modelo de riesgo y MLOps (MLflow, exportación, promoción y rollback), pantallas de Catálogo y Modelo |

## Arranque desde un clon limpio

Requisitos: Docker Desktop con Docker Compose.

```powershell
# Windows (PowerShell)
.\scripts\setup.ps1
docker compose up --build
```

```bash
# Linux / Mac
./scripts/setup.sh
docker compose up --build
```

`setup` genera, solo la primera vez, el archivo `.env` con contraseñas aleatorias y las llaves JWT en `secrets/`. Ninguno de los dos se sube al repositorio.

## Detener, conservar datos y experimentos

- `docker compose down` detiene todo y **conserva** los datos: PostgreSQL (`postgres_data`), RabbitMQ (`rabbitmq_data`) y los experimentos de MLflow (`mlflow_artifacts` para los artefactos y la base `mlflow` en PostgreSQL para ejecuciones, parámetros y métricas).
- `docker compose down -v` **borra** esos volúmenes: sirve para repetir la demostración desde cero (se vuelven a sembrar los productos, las existencias y las cuentas de prueba), pero se pierden las ejecuciones de MLflow. El modelo servido no depende de ellas: vive en `ml/registry/`, que está en el repositorio.
- `.env` y `secrets/` los crea `setup` y no se suben al repositorio. Si los borras, vuelve a ejecutar `setup`.
- Si cambias `.env` o el código de un servicio: `docker compose up -d --build <servicio>`.

## Puertos

| Componente | URL |
|---|---|
| **Aplicación web** | http://localhost:4200 |
| Productos | http://localhost:8001/docs |
| Clientes | http://localhost:8002/docs |
| Préstamos | http://localhost:8003/docs |
| Inventario | http://localhost:8004/docs |
| RabbitMQ (administración) | http://localhost:15672 |
| MLflow | http://localhost:5000 |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |

## Cuentas de demostración

Se crean al arrancar si `DEMO_TOKENS_ENABLED=true`. Las contraseñas están en tu `.env` (`DEMO_ADMIN_PASSWORD` y `DEMO_CLIENTE_PASSWORD`).

| Usuario | Rol | Cliente |
|---|---|---|
| `admin` | administrador | — |
| `ana` | cliente | `CLI-DEMO-0001` (perfil de bajo riesgo) |
| `beto` | cliente | `CLI-DEMO-0002` (perfil de alto riesgo) |

## Documentación

- [Decisiones de arquitectura](docs/decisiones.md)
- [Guía de demostración](docs/guia-demostracion.md)
- [Arquitectura y diagramas](docs/arquitectura.md)
- [Contratos REST y de mensajes](docs/contratos.md)
- [Mensajería (RabbitMQ, outbox, inbox)](docs/mensajeria.md)
- [Pruebas de aceptación](docs/aceptacion.md)
- [Plan de equipo](docs/plan-equipo.md)
- [Traspaso del frente de Juan David](docs/traspaso-companero.md)
- [Guía de lectura: Clientes](docs/guias/clientes.md)
- [Guía de lectura: Inventario](docs/guias/inventario.md)
- [Guía de lectura: Préstamos](docs/guias/prestamos.md)
- [Guía de lectura: Productos](docs/guias/productos.md)
- [Caché Redis: diseño, evidencia y mediciones](docs/redis-desempeno.md)
- [Modelo de riesgo: informe de selección](ml/reporte_seleccion.md)
- [Modelo de riesgo: datos (etapa A)](ml/reporte_datos.md) · [criterio de selección](ml/criterio_seleccion.md) · [drift (etapa F)](ml/reporte_drift.md)

## Demostración rápida

```powershell
.\scripts\demo-clientes.ps1        # login, autorización, CSV idempotente
.\scripts\demo-prestamos.ps1       # idempotencia y aislamiento de solicitudes
.\scripts\demo-flujo.ps1           # flujo completo por RabbitMQ, incluido un evento tardío
.\scripts\aceptacion-roles.ps1     # roles y aislamiento entre clientes
```

```bash
python scripts/evidencia_redis.py demo     # caché: miss, hit, expiración, cambio de precio, caída de Redis (pruebas 8 y 9)
ml/.venv/bin/python ml/scripts/prueba10.py # modelo exportado = POST /riesgo/predict (prueba 10)
ml/.venv/bin/python ml/scripts/prueba11.py # promoción v1 → v2 y rollback a v1 (prueba 11)
```
En Windows: `python scripts\evidencia_redis.py demo` y `ml\.venv\Scripts\python ml\scripts\prueba10.py`. Preparación del entorno de ML en [Pruebas de aceptación](docs/aceptacion.md#preparación-para-811).

Pruebas unitarias por servicio: `docker compose run --rm <servicio> pytest` (clientes, productos, prestamos, inventario).

Frontend en desarrollo (recarga en caliente): `cd frontend && npm install && npx ng serve`. Las URLs de las APIs se leen de `frontend/public/config.json`.

## Modelo de riesgo (MLOps)

El modelo activo es **v1**: regresión logística con `log1p` en las variables en pesos, elegida por *average precision* en validación entre 8 candidatos de 4 algoritmos registrados en MLflow. Umbral 0,25 elegido en validación con costos ficticios (aprobar a quien incumple = 3, rechazar a quien paga = 1); la partición de prueba se usó una sola vez (AP 0,511, ROC-AUC 0,686). **v2** (gradient boosting) es el retador usado para demostrar promoción y rollback. Detalle en el [informe de selección](ml/reporte_seleccion.md).

```
ml/registry/
├── active.json          versión activa + historial (solo lo escribe ml/scripts/promover.py)
├── v0-basico/           modelo provisional inicial
├── v1/                  pipeline.joblib, manifest.json, ejemplo_entrada.json, ejemplo_salida.json
└── v2/
```

- **Préstamos carga el modelo al iniciar**, desde la versión de `active.json`, y verifica el SHA-256 del artefacto contra el manifiesto. Después de promover, o de un `git pull` que cambie `ml/registry/`: `docker compose restart prestamos`.
- **Promover / rollback** (solo modifica `active.json`, valida el artefacto antes):
  ```bash
  python ml/scripts/promover.py estado
  python ml/scripts/promover.py promover v2 --motivo "..." --por "Nombre"
  python ml/scripts/promover.py rollback --motivo "..." --por "Nombre"
  docker compose restart prestamos
  ```
- **Reentrenar desde cero** (necesita el entorno de ML con Python 3.11 y MLflow en `http://localhost:5000`): la secuencia de comandos está en el §12 del [informe de selección](ml/reporte_seleccion.md#12-cómo-reproducir).
- En la aplicación, la pantalla **Modelo** (administrador) muestra la versión activa, el enlace al run de MLflow, las métricas, el historial de promociones, el uso por versión y una predicción manual.

## Caché Redis en Productos

`GET /productos/{id}` usa cache-aside (clave `productos:v1:{id}`, TTL 300 s, cabecera `X-Cache: HIT|MISS`); `PUT` y `DELETE` invalidan después del commit. **La cotización nunca usa la caché.** Si Redis cae, Productos responde desde PostgreSQL. Mediciones (p50 servidor: 0,09 ms HIT frente a 0,60 ms MISS; 98,6 % de aciertos) y los casos en que un dato puede estar desactualizado en [docs/redis-desempeno.md](docs/redis-desempeno.md).
