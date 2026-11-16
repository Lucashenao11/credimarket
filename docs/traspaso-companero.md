# Traspaso a [Compañero] — qué queda para ti

Fecha del traspaso: lunes 16 de noviembre de 2026, en la tarde. Entrega: **viernes 20 de noviembre**.
Lee primero `docs/plan-equipo.md` (contratos 4.1 a 4.3, convenciones de Git, reglas no negociables) y `docs/decisiones.md`.
Si usas un asistente de IA, dale esos dos documentos, este y el enunciado. Recuerda: en la sustentación tienes que poder explicar **todo lo tuyo**.

## 0. Lo primero (hoy, 30 minutos)

```powershell
git clone https://github.com/Lucashenao11/credimarket
cd credimarket
.\scripts\setup.ps1
Get-ChildItem -Recurse .\scripts -Filter *.ps1 | Unblock-File
docker compose up --build -d
.\scripts\demo-flujo.ps1        # el flujo completo; debe terminar sin errores
```

Pídele a Lucas la invitación al repositorio. Trabaja en ramas (`feat/redis`, `feat/ml`, `feat/frontend-catalogo`) y haz commits pequeños con prefijo (`feat:`, `test:`, `docs:`): el historial es la evidencia de tu contribución.

## 1. Qué ya está hecho (no lo rehagas)

- **Clientes, Inventario y Préstamos**, con RabbitMQ, outbox, consumidores idempotentes, máquina de estados y modelo cargado desde `ml/registry/active.json`. Todos con pruebas (`docker compose exec <servicio> pytest -q`).
- **Productos básico:** CRUD, desactivar, versión que sube en cada cambio, `GET /productos/{id}/cotizacion` (lee de PostgreSQL), 5 productos de ejemplo y 5 pruebas. **Sin Redis.**
- **Modelo base `v0-basico`** (regresión logística, ROC-AUC 0.69, umbral 0.5 provisional) en `ml/registry/v0-basico/`, generado con `ml/scripts/entrenar_basico.py`. Existe **solo para que Préstamos arranque**. Tu trabajo lo reemplaza.

## 2. Tu trabajo, en orden de prioridad

### 2.1 ML (criterios 4 y 5: 30 % de la nota) — es lo más importante, empieza por aquí

Detalle completo en `docs/plan-equipo.md`, secciones 4.3 y 5.3. Resumen de lo que se evalúa:

- **A. Datos:** validar `ml/data/prestamos_entrenamiento.csv` (tipos, rangos, faltantes, duplicados, balance), análisis exploratorio breve, hash SHA-256 del CSV, partición 60/20/20 estratificada con semilla fija (guarda los ids de cada partición), imputación/codificación/escalado **dentro del pipeline** y ajustados solo con entrenamiento.
- **B. Entrenamiento:** baseline trivial + al menos 3 algoritmos y 6 ejecuciones candidatas. **Escribe la métrica de selección y el desempate ANTES de comparar** (no uses accuracy). Métricas: precision, recall, F1 de la clase 1, ROC-AUC, average precision, matriz de confusión, Brier.
- **Umbral:** se elige sobre validación con costos ficticios explícitos y se **congela antes** de mirar la prueba. La partición de prueba se usa **una sola vez**.
- **C. MLflow** (`http://localhost:5000`): una ejecución por candidato con algoritmo, hiperparámetros, semilla, partición, hash de datos, características, commit del código, dependencias, duración, métricas y artefactos (pipeline, matriz de confusión, reporte).
- **D. Exportar y promover:** `ml/registry/v1/` y `v2/` con `pipeline.joblib`, `manifest.json` (campos exactos en plan-equipo 4.3), `ejemplo_entrada.json` y `ejemplo_salida.json`. Script de **promoción y rollback** que solo cambie `ml/registry/active.json`. Informe de selección en `ml/reporte_seleccion.md`.
- **F. Drift simulado:** PSI por variable entre `solicitudes_nuevas.csv` y el entrenamiento; reporte en `ml/`.
- **Prueba 10:** la probabilidad del pipeline exportado y la de `POST /riesgo/predict` de Préstamos deben ser **iguales** para el mismo ejemplo.

**Contrato que no puedes romper:** las 11 columnas de entrada, en ese orden y con esos nombres (ver `ml/scripts/entrenar_basico.py`, lista `FEATURES`); `clase_positiva = 1`; versiones fijas `scikit-learn==1.5.2`, `pandas==2.2.3`, `numpy==2.1.3`, `joblib==1.4.2`; `artefacto_sha256` correcto (Préstamos **rechaza arrancar** si no coincide). Si cambias una variable, avisa a Lucas el mismo día.

**Cómo probarlo con Préstamos:** copia tu versión a `ml/registry/<version>/`, cambia `active.json`, y `docker compose restart prestamos`. Revisa `GET /modelo/info` (necesita un token; ver `scripts/demo-prestamos.ps1`).

### 2.2 Redis en Productos (criterio 3: 10 %)

Busca `TODO(compañero)` en `services/productos/app/` y lee `docs/guias/productos.md`. Requisitos:
- Cache-aside con clave `productos:v1:{id}`, TTL definido y justificado; invalidar **después** del commit en `actualizar` y `desactivar`.
- Redis caído: timeout corto (≈100 ms) y respuesta desde PostgreSQL, sin error para el usuario.
- Cabecera `X-Cache: HIT|MISS` y una línea de log por consulta.
- **La cotización NO usa la caché** (es la fuente de verdad del monto).
- Evidencia: script en `scripts/` que muestre miss, hit, expiración, invalidación tras cambiar un precio y caída de Redis (`docker compose stop redis`); mediciones p50 y p95 con y sin caché, tasa de aciertos y `docker stats`; informe `docs/redis-desempeno.md` con claves, TTL, invalidación y cuándo el dato puede estar desactualizado.
- Pruebas automáticas de hit, miss e invalidación (agrega `redis` a `requirements.txt`).

### 2.3 Pantallas del frontend (parte del criterio 7)

El esqueleto de Angular **ya está en el repositorio** (`frontend/`): rutas con guardias por rol, sesión, interceptor del token, URLs configurables en `frontend/public/config.json`, y las pantallas de Lucas (login, solicitar, mis solicitudes, perfil, y administración de préstamos, inventario y clientes). Lucas dejó dos pantallas **básicas, de solo lectura**, con marcas `TODO(Juan David)` para que las completes:
- **Catálogo** (`frontend/src/app/pages/catalogo/`): hoy lista productos activos con enlace a "Solicitar". Falta: detalle de producto, mostrar versión, y vista de administrador para crear, actualizar y desactivar (`POST/PUT/DELETE /productos`).
- **Modelo (admin)** (`frontend/src/app/pages/admin/modelo/`): hoy muestra `GET /modelo/info` y el enlace a MLflow. Falta: historial de versiones promovidas, estadísticas de uso y enlace directo al run activo.

Para probar: `docker compose up -d --build frontend` y abre http://localhost:4200. Para desarrollar con recarga en caliente: `cd frontend && npm install && npx ng serve`.

## 3. Calendario comprimido

| Fecha | Meta |
|---|---|
| Lun 16 (tarde) | Entorno levantado, `demo-flujo.ps1` corre. ML etapa A (datos, hash, particiones) |
| **Mar 17, noche (control)** | Etapas B y C hechas en MLflow y **v1 exportada con manifiesto y promovida** (`active.json`). Redis con cache-aside básico |
| Mié 18 | v2, script de promoción/rollback, etapa F (drift), evidencia e informe de Redis. **Tarde:** prueba 10 con Lucas |
| Jue 19 | Pantallas de Catálogo y Modelo; `ml/reporte_seleccion.md` |
| Vie 20 | Tu parte de la documentación. Mañana: prueba desde clon limpio. Tarde: **simulacro cruzado** (cada uno explica lo del otro) |

Si el martes en la noche no hay v1 en `ml/registry/`, Lucas y tú replantean el ML entre los dos para no perder el 30 %. **Avisa el mismo día** si algo se atrasa.

## 4. Reglas que cuestan nota

Nada simulado; cero secretos en el repo (revisa `git status` antes de cada commit); `docker compose up` debe funcionar desde un clon limpio; el modelo se carga al iniciar desde una versión **promovida explícitamente**; ningún servicio consulta las tablas de otro.

## 5. Pendientes del equipo

- [ ] Tu nombre y usuario de GitHub para el README y la invitación.
- [ ] Correo al profesor registrando el grupo de dos integrantes.
