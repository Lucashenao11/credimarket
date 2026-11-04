# CrediMarket

Venta de productos tecnológicos a crédito: cuatro microservicios (Productos, Clientes, Préstamos e Inventario), frontend web, RabbitMQ, Redis, PostgreSQL y un modelo de riesgo con su ciclo MLOps en MLflow.

> Datos y operaciones de crédito ficticios. Se evalúa ingeniería de software y MLOps.

## Integrantes

| Integrante | Responsabilidades |
|---|---|
| Lucas | Todo el sistema: servicios, broker, Redis, frontend, modelo y MLOps |

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

## Puertos

| Componente | URL |
|---|---|
| Productos | http://localhost:8001/docs |
| Clientes | http://localhost:8002/docs |
| Préstamos | http://localhost:8003/docs |
| Inventario | http://localhost:8004/docs |
| RabbitMQ (administración) | http://localhost:15672 |
| MLflow | http://localhost:5000 |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |

## Documentación

- [Decisiones de arquitectura](docs/decisiones.md)
