# Guía de Préstamos

## Piezas tuyas (Corazón) — `TODO(Lucas)`
1. `app/estados.py`: la tabla `TRANSICIONES` (1a) y `cambiar_estado` (1b).
2. `app/idempotencia.py`: `hash_cuerpo` (2a) y `buscar_previa` (2b).
Pruebas: `docker compose exec prestamos pytest tests/test_estados.py tests/test_idempotencia.py -v`.

## Pegamento (léelo en este orden, con la pregunta al lado)
| Archivo | Pregunta |
|---|---|
| `solicitudes.py::crear_solicitud` | ¿En qué orden pasa todo, y por qué la consulta de la clave va ANTES de llamar a Clientes y Productos? |
| `solicitudes.py` (`except IntegrityError`) | ¿Qué petición gana si dos con la misma clave llegan a la vez? ¿Quién lo decide? |
| `eventos.py::reserva_confirmada` | ¿Qué devuelve si el préstamo ya está CANCELADA y por qué NO cambia el estado? |
| `reglas.py` | ¿Qué reglas rechazan antes de pedir inventario? |
| `riesgo.py::ModeloRiesgo` | ¿Qué pasa si alguien altera `pipeline.joblib`? |
| `integraciones.py` | ¿Por qué un fallo de Productos da 503 y no se decide con datos viejos? |

## Experimentos para romperlo (después de que pasen las pruebas)
- En `crear_solicitud`, mueve la llamada a `buscar_previa` DESPUÉS de consultar a Clientes/Productos. ¿Qué prueba falla y qué cambia en la práctica?
- Quita el `Prestamo.estado == esperado` del UPDATE. ¿Qué prueba lo detecta?
