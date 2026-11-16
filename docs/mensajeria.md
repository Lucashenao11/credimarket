# Mensajería (RabbitMQ)

## Topología
- Intercambio `credimarket` (direct, durable). Intercambio de mensajes muertos `credimarket.dlx`.
- Cola `inventario.comandos` (consume Inventario): `reserva.solicitada`, `reserva.liberar`, `salida.confirmar`.
- Cola `prestamos.eventos` (consume Préstamos): `inventario.reservado`, `inventario.insuficiente`, `reserva.vencida`, `salida.confirmada`.
- Cada cola tiene su cola de mensajes muertos `<cola>.dlq`. Tras 3 reintentos fallidos, el mensaje va ahí.

## Mensajes (sobre JSON: `message_id`, `tipo`, `payload`)
| Tipo | Lo publica | Payload | Efecto |
|---|---|---|---|
| ReservaSolicitada | Préstamos | prestamo_id, producto_id, cantidad | Inventario reserva |
| InventarioReservado | Inventario | prestamo_id | Préstamos: APROBADA |
| InventarioInsuficiente | Inventario | prestamo_id | Préstamos: CANCELADA_SIN_STOCK |
| LiberarReserva | Préstamos | prestamo_id, motivo | Inventario libera (cancelación, timeout o evento tardío) |
| ReservaVencida | Inventario | prestamo_id | Préstamos: CANCELADA (RESERVA_VENCIDA) |
| ConfirmarSalida | Préstamos | prestamo_id | Inventario confirma la salida |
| SalidaConfirmada | Inventario | prestamo_id | Préstamos: COMPLETADA |

## Garantías
- **Outbox:** el mensaje se escribe en la misma transacción que el cambio de negocio; un hilo lo publica con confirmación del broker. Si el servicio cae, el mensaje sigue en la base.
- **Al menos una vez:** un mensaje puede llegar repetido, nunca se pierde.
- **Consumidor idempotente:** la tabla `mensajes_procesados` (clave primaria `message_id`) más las restricciones del negocio (UNIQUE de la reserva, UPDATE condicional del estado).
- **Ack después del commit.**
- **ReservaVencida** se emite desde el *estado* de la reserva (id determinista `vencida-<prestamo_id>`), así sobrevive a una caída entre liberar y encolar.

## Casos
- Evento tardío (D6): `InventarioReservado` sobre un préstamo `CANCELADA` no lo reactiva; Préstamos encola `LiberarReserva`.
- Timeout (60 s sin respuesta): `CANCELADA / TIMEOUT_INVENTARIO` y `LiberarReserva` en la misma transacción.
