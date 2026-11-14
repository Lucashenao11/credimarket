# Guía de lectura — Servicio Clientes

Tiempo estimado: 45 minutos, más tu pieza (30 minutos).

## 1. El problema (antes de abrir código)

Clientes resuelve tres reglas del enunciado:
- **Sección 9, importación CSV:** importar dos veces el mismo archivo no duplica clientes; el reporte dice insertados, actualizados o rechazados y errores por fila.
- **Sección 9, autorización:** un cliente solo accede a sus propios datos; no basta con confiar en un `cliente_id` que llegue en la petición.
- **Decisión D5:** solo Clientes firma tokens (llave privada); los demás solo los verifican.

## 2. Orden de lectura (con una pregunta por archivo)

| # | Archivo | Pregunta que debes poder responder al terminar |
|---|---|---|
| 1 | `app/models.py` | ¿Qué columna tiene `unique=True` y por qué esa es la que impide duplicados, y no el código Python? |
| 2 | `app/schemas.py` | ¿Dónde se rechaza una fila con `tipo_empleo = pensionado`? ¿Y una con ingresos negativos? |
| 3 | `app/importacion.py` | ¿Por qué cada fila es su propia transacción? ¿Qué pasaría con las filas buenas si todo el archivo fuera una sola transacción y una fila fallara? |
| 4 | `app/security.py` | ¿Qué llave usa `emitir_token` y cuál usa `decodificar_token`? ¿Por qué `algorithms=["RS256"]` está fijo y no se lee del token? |
| 5 | `app/routers/clientes.py` | En `_puede_ver`, ¿de dónde sale el `cliente_id` con el que se compara: de la URL, del cuerpo de la petición o del token? ¿Por qué importa? |
| 6 | `app/routers/auth.py` | ¿Por qué el error es el mismo si el usuario no existe y si la contraseña está mal? |
| 7 | `app/seed.py` y `app/main.py` | ¿Cuándo se crean las tablas y las cuentas de demostración? |

## 3. Tu pieza: `insertar_si_no_existe` (en `app/importacion.py`)

1. Lee la docstring de la función y responde primero la pregunta que trae (en `docs/notas-estudio.md`).
2. Ejecuta las pruebas y míralas fallar:
   ```powershell
   docker compose up --build -d clientes
   docker compose exec clientes pytest -v
   ```
3. Escribe la función. Como el código se copia a la imagen al construirla, después de cada cambio vuelve a correr las dos líneas del paso 2.
4. Cuando pasen las 5 pruebas, corre la demostración completa:
   ```powershell
   .\scripts\demo-clientes.ps1
   ```

## 4. Rómpelo a propósito (predice antes de ejecutar)

Escribe tu predicción, ejecútalo y luego deshaz el cambio.

| Experimento | Tu predicción | Qué pasó |
|---|---|---|
| En `models.py`, quita `unique=True` de `cliente_id`, reconstruye y corre las pruebas (usan una base nueva en memoria, así que toman el cambio) | | |
| En tu función, quita el `db.rollback()` y corre las pruebas | | |
| Decodifica el token de ana en https://jwt.io (pégalo en el recuadro): ¿qué datos ves sin tener ninguna llave? ¿Podrías cambiar `rol` a `admin`? | | |
| Con PowerShell, pide los datos de beto usando el token de ana pero agregando `?cliente_id=CLI-DEMO-0002` a la URL | | |

## 5. Explícalo en 3 líneas (en `docs/notas-estudio.md`)

- Cómo garantiza la importación que no se dupliquen clientes, incluso con dos importaciones simultáneas.
- Qué pasa con una fila inválida y por qué no afecta a las demás.
- Por qué un cliente no puede ver los datos de otro aunque cambie la URL.
