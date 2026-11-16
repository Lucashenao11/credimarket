# Arquitectura de CrediMarket

Los diagramas están en Mermaid: GitHub los dibuja directamente al abrir este archivo.

## 1. Vista general

```mermaid
flowchart LR
  FE["Frontend Angular<br/>nginx :4200"]
  subgraph Servicios
    CL["Clientes :8002<br/>login, JWT, CSV"]
    PR["Productos :8001<br/>catálogo, cotización"]
    PM["Préstamos :8003<br/>flujo, estados, modelo"]
    IN["Inventario :8004<br/>reservas, movimientos"]
  end
  MQ{{"RabbitMQ<br/>exchange credimarket"}}
  RD[("Redis<br/>caché de Productos")]
  ML["MLflow :5000"]
  REG[/"ml/registry<br/>active.json + versiones"/]
  subgraph PostgreSQL
    D1[(clientes)]
    D2[(productos)]
    D3[(prestamos)]
    D4[(inventario)]
  end
  FE -->|HTTP + JWT| CL & PR & PM & IN
  PM -->|HTTP, token del usuario| CL
  PM -->|HTTP, cotización| PR
  PM <-->|comandos y eventos| MQ
  IN <-->|comandos y eventos| MQ
  PR --- RD
  PM -.->|carga al iniciar| REG
  ML -.->|exporta| REG
  CL --- D1
  PR --- D2
  PM --- D3
  IN --- D4
```

Reglas que sostienen el diseño: cada servicio solo lee **su** base de datos; entre servicios solo hay API HTTP o mensajes; el modelo se carga al iniciar desde la versión que apunta `active.json`, verificando el SHA-256 del artefacto.

## 2. Secuencia de una solicitud (camino feliz)

```mermaid
sequenceDiagram
  actor U as Cliente
  participant FE as Frontend
  participant PM as Préstamos
  participant CL as Clientes
  participant PR as Productos
  participant MQ as RabbitMQ
  participant IN as Inventario
  U->>FE: Enviar solicitud
  FE->>PM: POST /prestamos (Idempotency-Key)
  PM->>CL: perfil del cliente
  PM->>PR: cotización (precio, versión)
  PM->>PM: modelo de riesgo + reglas
  Note over PM: En UNA transacción: guarda PENDIENTE_INVENTARIO<br/>y el mensaje ReservaSolicitada (outbox)
  PM-->>FE: 202 PENDIENTE_INVENTARIO
  PM->>MQ: publica ReservaSolicitada (publisher confirm)
  MQ->>IN: reserva.solicitada
  IN->>IN: reserva atómica + inbox + outbox
  IN->>MQ: InventarioReservado
  MQ->>PM: inventario.reservado
  PM->>PM: UPDATE condicional → APROBADA
  FE->>PM: GET /prestamos (cada 3 s)
  PM-->>FE: APROBADA
```

Si no hay stock, Inventario publica `InventarioInsuficiente` y el préstamo pasa a `CANCELADA_SIN_STOCK`. Si Inventario no responde en 60 s, un temporizador lo cancela por `TIMEOUT_INVENTARIO` y publica `LiberarReserva` en la misma transacción.

## 3. Máquina de estados del préstamo

```mermaid
stateDiagram-v2
  [*] --> RECHAZADA: riesgo alto o regla de negocio
  [*] --> PENDIENTE_INVENTARIO: riesgo favorable
  PENDIENTE_INVENTARIO --> APROBADA: InventarioReservado
  PENDIENTE_INVENTARIO --> CANCELADA_SIN_STOCK: InventarioInsuficiente
  PENDIENTE_INVENTARIO --> CANCELADA: usuario, timeout o reserva vencida
  APROBADA --> COMPLETADA: SalidaConfirmada (entrega)
  APROBADA --> CANCELADA: usuario o reserva vencida
  RECHAZADA --> [*]
  CANCELADA_SIN_STOCK --> [*]
  CANCELADA --> [*]
  COMPLETADA --> [*]
```

Cada cambio es un `UPDATE ... WHERE estado = <esperado>`: si dos eventos compiten, solo uno cambia el estado. Un evento tardío **nunca reactiva** un préstamo ya final; Préstamos publica `LiberarReserva` para deshacer la reserva.

## 4. Mensajería y garantías

```mermaid
flowchart LR
  PM["Préstamos<br/>outbox"] -->|reserva.solicitada<br/>reserva.liberar<br/>salida.confirmar| E{{"exchange credimarket"}}
  IN["Inventario<br/>outbox"] -->|inventario.reservado<br/>inventario.insuficiente<br/>reserva.vencida<br/>salida.confirmada| E
  E --> QI["inventario.comandos"] --> IN
  E --> QP["prestamos.eventos"] --> PM
  QI -. "tras 3 reintentos" .-> DX{{"credimarket.dlx"}}
  QP -. "tras 3 reintentos" .-> DX
  DX --> DLQ[["colas .dlq"]]
```

- **Outbox transaccional:** el mensaje se guarda en la misma transacción que el cambio de estado; un publicador lo envía con *publisher confirms*. Entrega **al menos una vez**.
- **Inbox:** `mensajes_procesados(message_id)` descarta duplicados. El *ack* se envía **después** del commit.
- **Reintentos:** hasta 3 (cabecera `x-reintentos`); después `nack` sin reencolar y el mensaje va a la cola de mensajes muertos.
- Detalle completo en [mensajeria.md](mensajeria.md); decisiones y su razón en [decisiones.md](decisiones.md).
