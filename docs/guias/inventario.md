# Guía de lectura — Servicio Inventario

Tiempo estimado: 30 minutos de lectura, más tus dos piezas (1 a 1.5 horas).

## 1. El problema (antes de abrir código)

- **Sección 1 del enunciado:** "dos clientes quieren comprar el último computador y ambos reciben la aprobación". Inventario es donde esto se resuelve.
- **Sección 3:** la reserva debe ser atómica y nunca puede generar existencias negativas.
- **Pruebas de aceptación 3, 4, 5 y 7:** sin stock, última unidad, mensaje repetido, cancelación.
- **Decisión D6:** las reservas vencen (60 s en la demo).

Las mismas ideas que ya conoces, ahora en Python:

| Lo que practicaste | Dónde aparece aquí |
|---|---|
| `UPDATE ... WHERE saldo >= 400` (billetera, A3) | Reservar: `WHERE disponible >= cantidad` |
| `UNIQUE` sobre `cliente_id` (Clientes, hoy) | `UNIQUE` sobre `prestamo_id` en reservas |
| `rollback` para limpiar la sesión (hoy) | Después de `INSUFICIENTE` y de `YA_PROCESADA` |

## 2. Orden de lectura

| # | Archivo | Pregunta que debes poder responder |
|---|---|---|
| 1 | `app/models.py` | ¿Qué hacen los dos `CheckConstraint` de `Existencia`? Si tu código tuviera un error y restara de más, ¿quién lo detendría? |
| 2 | `app/models.py` | ¿Qué columna de `Reserva` tiene `unique=True`, y qué prueba de aceptación protege? |
| 3 | `app/reservas.py`, `registrar_entrada` | ¿Por qué el `UPDATE` usa `Existencia.disponible + cantidad` en vez de leer el valor, sumarlo en Python y escribirlo? (Recuerda la "actualización perdida" de A3) |
| 4 | `app/reservas.py`, `confirmar_salida` | Es el **modelo** para tu `liberar`: un `UPDATE` de la reserva que solo cambia la fila si `estado == "ACTIVA"`, y `rowcount` para saber si lo logró |
| 5 | `app/reservas.py`, `vencer_reservas` | ¿Qué función tuya reutiliza? ¿Qué pasa si una reserva se confirma justo antes de vencer? |
| 6 | `app/vencimiento.py` y `app/main.py` | ¿Cada cuánto se revisan las reservas vencidas, y dónde se inicia ese hilo? |
| 7 | `app/routers/inventario.py` | ¿Por qué todo el router exige rol `admin`? ¿Por qué ya no existen los endpoints `/pruebas`? |

## 3. Tus piezas

**Primero `reservar`, después `liberar`.** Las pruebas de `liberar`, `vencer_reservas` y la del invariante solo pasan cuando las dos están listas.

```powershell
docker compose up --build -d inventario
docker compose exec inventario pytest -v
```

Cuando pasen las 11:

```powershell
.\scripts\demo-inventario.ps1
```

Ese script hace la prueba 4 de verdad: 10 procesos piden la última unidad en el mismo instante, contra PostgreSQL. Debe haber exactamente 1 reservada.

## 4. Rómpelo (predice antes de ejecutar)

| Experimento | Tu predicción | Qué pasó |
|---|---|---|
| En `reservar`, quita la condición `Existencia.disponible >= cantidad` del `where` y corre las pruebas | | |
| Igual que el anterior, pero corre `demo-inventario.ps1`. ¿Qué detiene ahora el stock negativo? Mira el error en `docker compose logs inventario --tail 30` | | |
| En `liberar`, quita la condición `Reserva.estado == "ACTIVA"` del `where` | | |

## 5. Explícalo en 3 líneas (en `docs/notas-estudio.md`)

- Por qué, con 10 peticiones simultáneas por la última unidad, solo una la obtiene.
- Qué impide que un mensaje de reserva repetido descuente las unidades dos veces.
- Qué impide que una cancelación repetida devuelva las unidades dos veces.
