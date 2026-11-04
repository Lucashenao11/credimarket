# Plan de equipo — CrediMarket

Documento de coordinación entre los dos integrantes. Léelo completo antes de escribir código. Si usas un asistente de IA, dale este documento, el enunciado (`Enunciado_CrediMarket.docx`) y `docs/decisiones.md`.

## 1. Contexto

- **Entrega:** lunes 9 de noviembre de 2026, 11:59 p. m. Repositorio Git + demostración en vivo.
- **Integrantes:** Lucas y [Compañero]. El enunciado exige que **cualquiera de los dos pueda explicar cualquier parte** del sistema; la nota individual puede bajar si no. Por eso, antes del lunes cada uno le explica al otro su parte (ver sección 8).
- **Decisiones ya tomadas:** D1 a D8 en `docs/decisiones.md` (RabbitMQ, FastAPI síncrono, una instancia de PostgreSQL con 4 bases aisladas, Angular, JWT RS256, tiempos de espera, promoción con `active.json`, secretos generados por script). No se cambian sin acordarlo entre los dos.

## 2. Reglas no negociables

Cualquiera de estas convierte un criterio en 0 % o lo topa:

1. **Nada simulado:** ni respuestas quemadas en el frontend, ni aprobaciones sin reserva real, ni broker de adorno.
2. **Cero secretos en el repositorio.** `.env` y `secrets/` están en `.gitignore`; solo se sube `.env.example`. Un secreto en el repo deja el criterio 6 en máximo 40 %.
3. **`docker compose up` debe levantar todo desde un clon limpio** (después de `scripts/setup`).
4. **Deduplicación durable en base de datos**, nunca solo en Redis o en memoria.
5. **El modelo se carga al iniciar, desde una versión promovida explícitamente**, nunca "el último archivo".
6. **Nunca consultar las tablas de otro servicio:** solo API o mensajes.

## 3. División del trabajo

| Integrante | Alcance | Criterios de la rúbrica |
|---|---|---|
| **[Compañero]** | Servicio **Productos** + **Redis** (cache-aside, mediciones, informe); **ML completo** (etapas A a F, MLflow, exportación, manifiesto, promoción y rollback); pantallas de **Catálogo** y **Modelo (admin)** del frontend | 3 (10 %), 4 (15 %), 5 (15 %) + parte del 7 |
| **Lucas** | Servicios **Clientes** (importación CSV, emisión de tokens), **Préstamos** (flujo, máquina de estados, carga y uso del modelo, endpoints de la API del modelo), **Inventario** (reserva atómica); **RabbitMQ**, outbox y consumidores idempotentes; esqueleto del frontend y las demás pantallas; documentación general | 1 (15 %), 2 (15 %), 6 (15 %), 8 (5 %) + resto del 7 |

Los dos frentes se tocan solo en los **tres contratos** de la sección 4. Mientras se respeten, nadie bloquea a nadie.

## 4. Contratos entre los dos frentes

### 4.1 JWT (lo emite Clientes, lo valida cada servicio)

- Algoritmo **RS256**. Clientes firma con la llave privada; los demás validan con la pública, montada en `/run/secrets/jwt_public.pem` (variable `JWT_PUBLIC_KEY_PATH`).
- Claims:

```json
{
  "sub": "usuario-123",
  "rol": "cliente",
  "cliente_id": "CLI-0000001",
  "iss": "credimarket-clientes",
  "aud": "credimarket",
  "iat": 1793805000,
  "exp": 1793808600
}
```

- `rol` es `cliente`, `admin` o `servicio` (este último, para llamadas entre servicios). `cliente_id` solo viene cuando `rol = cliente`.
- Validación en FastAPI con `PyJWT[crypto]`: verificar firma, `exp`, `iss` y `aud`. Token inválido o vencido → **401**; rol sin permiso → **403**.
- En Productos: consultar es para cualquier usuario autenticado; crear, actualizar y desactivar es solo para `admin`.
- Mientras Lucas termina la emisión en Clientes (jueves en la noche), puedes generar tokens de prueba localmente con la llave privada de tu carpeta `secrets/`.

### 4.2 Cotización (Productos → Préstamos)

```
GET /productos/{producto_id}/cotizacion
Authorization: Bearer <token con rol servicio, admin o cliente>
```

```json
{
  "producto_id": 12,
  "nombre": "Portátil 14 pulgadas",
  "precio_cop": 3200000,
  "version": 4,
  "activo": true,
  "consultado_en": "2026-11-07T15:04:05Z"
}
```

- **Se lee siempre de PostgreSQL, nunca de Redis.** Es la fuente de verdad del precio con el que se calcula el monto del préstamo (enunciado, sección 6).
- `version` es un entero que **aumenta en cada cambio** del producto (precio, nombre, categoría o estado). Préstamos guarda el precio y la versión usados.
- Producto inexistente → 404. Producto desactivado → 200 con `"activo": false` (Préstamos lo rechaza).

### 4.3 Modelo exportado (ML → Préstamos)

**Estructura de carpetas:**

```
ml/registry/
├── active.json
├── v1/
│   ├── pipeline.joblib
│   ├── manifest.json
│   ├── ejemplo_entrada.json
│   └── ejemplo_salida.json
└── v2/
    └── ...
```

**`active.json`** (lo escribe solo el script de promoción):

```json
{
  "model_version": "v1",
  "promovido_en": "2026-11-07T18:00:00Z",
  "promovido_por": "nombre",
  "version_anterior": null,
  "motivo": "Primera versión"
}
```

**`manifest.json`** debe incluir: `model_version`, `run_id` de MLflow, `dataset_version` y `dataset_sha256`, `features` (nombre y tipo, en orden), `clase_positiva` (1 = incumplimiento a 90 días), `umbral`, métricas de validación y de prueba, dependencias con versión (`scikit-learn`, `pandas`, `numpy`, `joblib`) y `artefacto_sha256` (hash de `pipeline.joblib`).

**Entradas del pipeline** (un `DataFrame` de pandas con exactamente estas columnas; el pipeline incluye imputación, codificación y escalado):

| Columna | Tipo | Faltantes permitidos | Origen en Préstamos |
|---|---|---|---|
| `ingresos_mensuales_cop` | float | No | Clientes |
| `obligaciones_mensuales_cop` | float | No | Clientes |
| `tipo_empleo` | str: `dependiente`, `independiente`, `temporal` | Sí | Clientes |
| `antiguedad_laboral_meses` | float | Sí | Clientes |
| `meses_historial_crediticio` | float | Sí | Clientes |
| `creditos_previos` | int | No | Clientes |
| `atrasos_previos_30d` | int | No | Clientes |
| `porcentaje_pago_puntual` | float | Sí (sin historial) | Clientes |
| `monto_solicitado_cop` | float | No | precio de la cotización × cantidad |
| `plazo_meses` | int | No | solicitud |
| `cuota_estimada_cop` | float | No | calculada con la fórmula de abajo |

- **Excluidas:** `solicitud_id` y `cliente_id` (identificadores), `incumplimiento_90d` (etiqueta) y `tasa_mensual_simulada` (constante, 0.018; justificar en el informe). Si el análisis exploratorio muestra que conviene quitar o transformar otra variable (por ejemplo, por redundancia con `cuota_estimada_cop`), se puede, **siempre que se avise a Lucas y se actualice esta tabla**, porque Préstamos construye estas mismas columnas.
- **Fórmula de la cuota** (verificada contra el CSV: con 7 464 000, 6 meses y 0.018 da 1 323 536.90):

```
cuota = monto × i / (1 − (1 + i)^(−n)),   con i = 0.018 y n = plazo_meses
```

- **Salida:** `pipeline.predict_proba(df)[:, 1]` es la probabilidad de incumplimiento. La decisión de riesgo se toma comparándola con el `umbral` del manifiesto.
- **Versiones fijas:** las mismas de `ml/requirements.txt` deben ir en `services/prestamos/requirements.txt`. Usa `scikit-learn==1.5.2`, `pandas==2.2.3`, `numpy==2.1.3`, `joblib==1.4.2`.

## 5. Alcance detallado de [Compañero]

### 5.1 Servicio Productos (carpeta `services/productos`)

- CRUD: crear, listar, consultar, actualizar y desactivar productos, con nombre, categoría, precio en COP y versión.
- Cache-aside con Redis:
  - Clave: `productos:v1:{producto_id}`. TTL: definirlo y justificarlo (por ejemplo, 300 s).
  - Lectura: Redis primero; si no está, PostgreSQL y luego guardar en Redis con TTL.
  - Escritura: invalidar la clave **después** del commit en PostgreSQL.
  - Redis caído: timeout corto (por ejemplo, 100 ms) y respuesta desde PostgreSQL, sin error para el usuario.
  - Evidencia visible: cabecera `X-Cache: HIT` o `MISS` y una línea de log por consulta.
- El endpoint de cotización del contrato 4.2.
- Datos iniciales: un script o migración con unos 10 productos de ejemplo.

### 5.2 Evidencia de Redis (criterio 3)

- Script en `scripts/` que demuestre: miss, hit, expiración, invalidación tras cambiar un precio y caída de Redis (`docker compose stop redis`).
- Mediciones p50 y p95 con y sin caché, tasa de aciertos y recursos consumidos (`docker stats`).
- Informe en `docs/redis-desempeno.md`: claves, TTL, invalidación, cuándo puede haber un dato desactualizado y análisis de las mediciones.

### 5.3 ML, etapas A a F (criterios 4 y 5), carpeta `ml/`

- **A. Datos:** validación (tipos, rangos, faltantes, duplicados, balance de clases), análisis exploratorio breve, hash SHA-256 del CSV, particiones 60/20/20 estratificadas con semilla fija, identificadores de cada partición guardados. Imputadores, codificadores y escaladores **ajustados solo con entrenamiento**, dentro del pipeline.
- **B. Entrenamiento:** un baseline trivial y al menos 3 algoritmos (por ejemplo, regresión logística, árbol de decisión y random forest), con al menos 6 ejecuciones candidatas además del baseline. **Antes de comparar**, escribir la métrica de selección y el criterio de desempate. No seleccionar por accuracy.
- **Métricas:** precision, recall y F1 de la clase 1, ROC-AUC, average precision, matriz de confusión y Brier score.
- **Umbral:** se ajusta sobre validación con una curva de costos ficticios explícitos (aprobar a quien incumplirá vs. rechazar a quien habría pagado) y se **congela antes** de mirar la partición de prueba. La prueba se usa una sola vez, con el modelo seleccionado.
- **C. MLflow:** cada ejecución en `http://localhost:5000` con algoritmo, hiperparámetros, semilla, estrategia de partición, hash de los datos, lista de características, commit del código, parámetros de preprocesamiento, dependencias, duración, métricas y artefactos (pipeline, matriz de confusión, reporte).
- **D. Exportar y promover:** pipeline completo según el contrato 4.3, manifiesto, ejemplos de entrada y salida, **dos versiones** (v1 y v2) y un script de promoción y rollback que solo modifique `active.json`. Informe de selección en `ml/reporte_seleccion.md`.
- **E. Servir:** lo implementa Lucas en Préstamos, a partir del contrato 4.3. Tú verificas la prueba 10: las predicciones del pipeline exportado y las de la API deben ser iguales.
- **F. Monitoreo y drift simulado:** comparar la distribución de `solicitudes_nuevas.csv` contra la de entrenamiento (por ejemplo, PSI por variable) y dejar el reporte en `ml/`.
- Entorno: un `venv` local con `ml/requirements.txt`; MLflow corre en el compose (`MLFLOW_TRACKING_URI=http://localhost:5000`).

### 5.4 Frontend

Lucas crea el esqueleto de Angular (rutas, sesión, interceptor del token y URLs configurables) a más tardar el **viernes 6 al mediodía**. Tú agregas:
- **Catálogo:** listado y detalle con precio; selección de cantidad y plazo que lleva a la solicitud; vista admin para crear, actualizar y desactivar.
- **Modelo (admin):** versión activa, run ID y umbral (desde `GET /modelo/info` de Préstamos) y enlace a MLflow.

## 6. Convenciones de Git

- Un solo repositorio en GitHub; Lucas lo crea y te invita.
- Una rama por frente: `feat/productos-redis`, `feat/ml`, `feat/frontend-catalogo`. Se integra a `main` con pull request; el otro le da una revisión rápida.
- Commits pequeños y frecuentes, con prefijo: `feat:`, `fix:`, `docs:`, `chore:`, `test:`. Nada de un commit gigante al final: el historial es evidencia de la contribución de cada uno.
- Antes de cada commit: `git status`, y verificar que no aparezcan `.env` ni archivos de `secrets/`.
- Antes de empezar el día: `git pull --rebase origin main`.
- No modificar carpetas del otro frente sin avisar. Los archivos compartidos (`docker-compose.yml`, `README.md`, `docs/decisiones.md`) se cambian en pull requests pequeños.

## 7. Cómo arrancar

```powershell
git clone <url-del-repo>
cd credimarket
.\scripts\setup.ps1      # en Linux/Mac: ./scripts/setup.sh
docker compose up --build -d
.\scripts\verificar-dia1.ps1
```

Si PowerShell bloquea los scripts: `Get-ChildItem -Recurse .\scripts -Filter *.ps1 | Unblock-File`.

## 8. Calendario e hitos de integración

| Fecha | [Compañero] | Lucas | Hito conjunto |
|---|---|---|---|
| Mié 4 | Clonar y levantar el entorno; etapa A del ML | Cierre del Día 1; Clientes | — |
| Jue 5 | Productos con CRUD y cache-aside | Clientes con CSV y emisión de tokens (Lucas sustenta otra materia a las 2 p. m.) | **Noche:** el contrato de cotización (4.2) responde |
| Vie 6 | Etapas B y C en MLflow | Inventario y Préstamos, broker y outbox; esqueleto del frontend al mediodía | — |
| Sáb 7 | Etapa D: v1 exportada y promovida | Préstamos carga el modelo; endpoints de la API del modelo | **Tarde:** prueba 10 (pipeline vs. API) |
| Dom 8 | v2, promoción y rollback; etapa F; evidencia e informe de Redis; pantallas de catálogo y modelo | Frontend restante, autenticación por rol, pruebas de aceptación | **Noche:** flujo completo desde el navegador |
| Lun 9 | Documentación de su frente | README, diagramas, guía de demostración | **Mañana:** prueba desde clon limpio. **Tarde:** cada uno explica la parte del otro (simulacro cruzado). **11:59 p. m.:** entrega |

Si alguien se atrasa, avisa el mismo día. Lo primero que se recorta es lo opcional; nunca el flujo de las pruebas de aceptación.

## 9. Pendiente

- [ ] Nombre y usuario de GitHub de [Compañero] (para el README y la invitación al repositorio).
- [ ] Correo al profesor registrando el grupo de dos integrantes.
