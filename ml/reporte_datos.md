# Etapa A — Validación y análisis exploratorio de los datos

Generado por `ml/scripts/etapa_a_datos.py` el 2026-11-16T22:21:59+00:00. No editar a mano.

## Identificación del conjunto de datos

- Archivo: `ml/data/prestamos_entrenamiento.csv`
- SHA-256: `c6cdc437c3aecc9116bc8b978df421d5a7600634c1ad7d6f82e58222a2446ecd`
- Filas: 12,000; columnas: 15
- Clase positiva (1 = incumplimiento a 90 días): 3,667 (30.6%). Desbalance moderado (≈ 1:2.3): no se usa accuracy (un modelo que siempre dice 0 tendría 69.4%).

## Validación

Resultado: **sin errores**.

| Comprobación | Resultado |
|---|---|
| Columnas esperadas presentes | sí |
| `solicitud_id` duplicados | 0 |
| Clientes con más de una solicitud | 0 |
| Filas duplicadas (completas / sin identificadores) | 0 / 0 |
| Mismas variables con etiqueta distinta | 0 |
| Valores fuera de rango | 0 |
| `tipo_empleo` fuera de ['dependiente', 'independiente', 'temporal'] | 0 |
| `tasa_mensual_simulada` constante = 0.018 | sí |
| Error relativo máximo de `cuota_estimada_cop` vs. la fórmula | 2.5e-07 |
| Obligaciones > ingresos | 0 |

Rangos comprobados: `ingresos_mensuales_cop` ∈ [1, ∞]; `obligaciones_mensuales_cop` ∈ [0, ∞]; `antiguedad_laboral_meses` ∈ [0, 600]; `meses_historial_crediticio` ∈ [0, 600]; `creditos_previos` ∈ [0, ∞]; `atrasos_previos_30d` ∈ [0, ∞]; `porcentaje_pago_puntual` ∈ [0, 100]; `monto_solicitado_cop` ∈ [1, ∞]; `cuota_estimada_cop` ∈ [1, ∞].

### Faltantes

| Variable | Faltantes | % | Permitido por el contrato |
|---|---|---|---|
| `tipo_empleo` | 93 | 0.78% | sí |
| `antiguedad_laboral_meses` | 91 | 0.76% | sí |
| `meses_historial_crediticio` | 97 | 0.81% | sí |
| `porcentaje_pago_puntual` | 2,473 | 20.61% | sí |

`porcentaje_pago_puntual` falta en 2,473 filas con `creditos_previos = 0` y en 0 filas con créditos; hay 0 filas sin créditos que sí lo tengan. Es un faltante **estructural** (no hay historial que medir), no aleatorio.

## Decisiones de preprocesamiento (dentro del pipeline, ajustadas solo con entrenamiento)

- **Variables excluidas:** `solicitud_id` (identificador); `cliente_id` (identificador); `tasa_mensual_simulada` (constante (0.018): varianza cero, no aporta información); `incumplimiento_90d` (etiqueta).
- **Numéricas:** imputación por mediana (robusta a la asimetría de las variables en COP) + indicador de faltante (`add_indicator=True`), para no hacer pasar a un cliente sin historial por uno con historial mediano; luego `StandardScaler` (necesario para la regresión logística; inocuo para árboles).
- **Categórica (`tipo_empleo`):** faltante → categoría explícita `"desconocido"` y one-hot con `handle_unknown="ignore"`. Se prefiere a la moda porque los faltantes incumplen más que la moda (ver tabla abajo; n pequeño, evidencia débil) y porque no inventa un dato. Dos imputadores en cadena (uno para `NaN`, otro para `None`) garantizan que la API y la solicitud real den la misma probabilidad (prueba 10).
- **Particiones antes de cualquier ajuste:** la mediana, la media y la desviación del escalado y las categorías del one-hot se calculan con `fit` sobre entrenamiento únicamente; validación y prueba solo pasan por `transform`. Así no hay fuga de información.

## Particiones

Estratificadas por la etiqueta, semilla `42`. Como cada cliente tiene una sola solicitud, no hace falta partir por grupos. Identificadores en `ml/data/particiones.csv` (SHA-256 `b6a0394eb4ae533ee306db5a2c1b28d933376b7f66f68b5296c4668541eb7b4c`).

| particion | filas | incumplimientos | tasa |
|---|---|---|---|
| entrenamiento | 7200 | 2200 | 30.56 % |
| validacion | 2400 | 734 | 30.58 % |
| prueba | 2400 | 733 | 30.54 % |

Uso: **entrenamiento** para ajustar; **validación** para comparar candidatos y elegir el umbral; **prueba** una sola vez, con el modelo y el umbral ya congelados.

## Análisis exploratorio

### Resumen de variables numéricas

| index | count | faltantes | mean | std | min | 1% | 50% | 99% | max | asimetria |
|---|---|---|---|---|---|---|---|---|---|---|
| ingresos_mensuales_cop | 12000.0 | 0 | 4828941.33 | 3385127.9 | 1400000.0 | 1400000.0 | 3905000.0 | 17539350.0 | 28000000.0 | 2.17 |
| obligaciones_mensuales_cop | 12000.0 | 0 | 1368149.33 | 1313408.05 | 11000.0 | 73990.0 | 972000.0 | 6450390.0 | 16485000.0 | 2.68 |
| antiguedad_laboral_meses | 11909.0 | 91 | 37.38 | 28.33 | 0.0 | 2.0 | 31.0 | 133.0 | 240.0 | 1.57 |
| meses_historial_crediticio | 11903.0 | 97 | 56.38 | 38.82 | 0.0 | 4.0 | 48.0 | 184.0 | 300.0 | 1.33 |
| creditos_previos | 12000.0 | 0 | 2.37 | 2.23 | 0.0 | 0.0 | 2.0 | 10.0 | 19.0 | 1.37 |
| atrasos_previos_30d | 12000.0 | 0 | 0.78 | 1.22 | 0.0 | 0.0 | 0.0 | 6.0 | 12.0 | 2.39 |
| porcentaje_pago_puntual | 9527.0 | 2473 | 83.47 | 12.02 | 12.68 | 47.94 | 86.09 | 99.5 | 99.97 | -1.03 |
| monto_solicitado_cop | 12000.0 | 0 | 4025144.17 | 2912489.42 | 500000.0 | 624970.0 | 3200000.0 | 15000000.0 | 15000000.0 | 1.63 |
| plazo_meses | 12000.0 | 0 | 19.82 | 9.18 | 6.0 | 6.0 | 18.0 | 36.0 | 36.0 | 0.34 |
| cuota_estimada_cop | 12000.0 | 0 | 310719.31 | 307864.88 | 18991.92 | 33072.77 | 214888.96 | 1497552.56 | 2659841.03 | 2.95 |

### Incumplimiento por variable categórica y por plazo

| tipo_empleo | n | tasa_incumplimiento |
|---|---|---|
| (faltante) | 93 | 34.4 % |
| dependiente | 6765 | 27.9 % |
| independiente | 3461 | 32.3 % |
| temporal | 1681 | 37.4 % |

| plazo_meses | n | tasa_incumplimiento |
|---|---|---|
| 6 | 1397 | 39.6 % |
| 12 | 2910 | 31.8 % |
| 18 | 2130 | 31.1 % |
| 24 | 3673 | 27.6 % |
| 36 | 1890 | 27.2 % |

### Incumplimiento por quintil (variables clave)

**ingresos_mensuales_cop**

| ingresos_mensuales_cop | n | tasa_incumplimiento |
|---|---|---|
| (1399999.999, 2258800.0] | 2400 | 38.6 % |
| (2258800.0, 3283600.0] | 2400 | 32.7 % |
| (3283600.0, 4615000.0] | 2402 | 29.4 % |
| (4615000.0, 6772200.0] | 2398 | 28.5 % |
| (6772200.0, 28000000.0] | 2400 | 23.6 % |

**atrasos_previos_30d**

| atrasos_previos_30d | n | tasa_incumplimiento |
|---|---|---|
| (-0.001, 1.0] | 9774 | 26.5 % |
| (1.0, 12.0] | 2226 | 48.5 % |

**porcentaje_pago_puntual**

| porcentaje_pago_puntual | n | tasa_incumplimiento |
|---|---|---|
| (12.679, 73.842] | 1906 | 44.1 % |
| (73.842, 82.74] | 1907 | 33.0 % |
| (82.74, 88.976] | 1903 | 31.2 % |
| (88.976, 94.11] | 1906 | 24.9 % |
| (94.11, 99.97] | 1905 | 23.6 % |
| nan | 2473 | 27.6 % |

**carga_obligaciones**

| carga_obligaciones | n | tasa_incumplimiento |
|---|---|---|
| (0.00113, 0.138] | 2400 | 20.4 % |
| (0.138, 0.222] | 2400 | 25.3 % |
| (0.222, 0.31] | 2400 | 29.1 % |
| (0.31, 0.421] | 2400 | 34.5 % |
| (0.421, 0.891] | 2400 | 43.6 % |

**carga_cuota**

| carga_cuota | n | tasa_incumplimiento |
|---|---|---|
| (0.00030999999999999995, 0.0223] | 2400 | 23.4 % |
| (0.0223, 0.0419] | 2400 | 27.0 % |
| (0.0419, 0.0719] | 2400 | 29.2 % |
| (0.0719, 0.134] | 2400 | 31.0 % |
| (0.134, 1.671] | 2400 | 42.1 % |

**Sin historial crediticio (porcentaje_pago_puntual faltante)**

| sin_historial | n | tasa_incumplimiento |
|---|---|---|
| False | 9527 | 31.3 % |
| True | 2473 | 27.6 % |

### Correlación de Spearman con la etiqueta

| index | rho_spearman |
|---|---|
| atrasos_previos_30d | 0.199 |
| carga_obligaciones | 0.179 |
| porcentaje_pago_puntual | -0.154 |
| carga_cuota | 0.135 |
| ingresos_mensuales_cop | -0.106 |
| cuota_estimada_cop | 0.095 |
| plazo_meses | -0.073 |
| monto_solicitado_cop | 0.067 |
| creditos_previos | 0.064 |
| antiguedad_laboral_meses | -0.06 |
| obligaciones_mensuales_cop | 0.051 |
| meses_historial_crediticio | 0.022 |

### Pares de variables de entrada con |rho| ≥ 0,6 (redundancia)

| variable_a | variable_b | rho |
|---|---|---|
| ingresos_mensuales_cop | obligaciones_mensuales_cop | 0.672 |
| meses_historial_crediticio | creditos_previos | 0.698 |
| monto_solicitado_cop | cuota_estimada_cop | 0.829 |

## Solicitudes nuevas (para la etapa F)

`ml/data/solicitudes_nuevas.csv`: 200 filas, SHA-256 `1430d7b34e924d5e4170c4fb9d9a412c1000af17c062af513ef15e44a1a7f1f7`, sin errores de validación. Faltantes: `tipo_empleo` 2, `antiguedad_laboral_meses` 1, `meses_historial_crediticio` 1, `porcentaje_pago_puntual` 43.
