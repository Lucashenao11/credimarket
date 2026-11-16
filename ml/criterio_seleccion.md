# Criterio de selección y de umbral (fijado ANTES de comparar candidatos)

Escrito el 16 de noviembre de 2026, antes de entrenar cualquier candidato. Cada ejecución de MLflow
registra el SHA-256 de este archivo (`criterio_sha256`): si se cambiara después de ver resultados,
el hash no coincidiría.

## 1. Métrica de selección

**Average precision (AP, área bajo la curva precisión-recall) en la partición de validación**, clase positiva 1.

Por qué:
- No depende del umbral: compara la capacidad de ordenar a los solicitantes por riesgo, y el umbral se
  elige después con costos.
- Con 30,6 % de positivos, AP se concentra en la clase que importa (incumplimiento). ROC-AUC se reporta,
  pero es menos sensible a cómo le va al modelo con los positivos.
- Accuracy queda descartada: un modelo que aprueba a todos tiene 69,4 %.

## 2. Desempate

1. Si dos candidatos quedan a **menos de 0,005 de AP**, gana el de **menor Brier score** en validación
   (probabilidades mejor calibradas: Préstamos muestra la probabilidad, no solo la decisión).
2. Si la diferencia de Brier también es menor a 0,002, gana el **más simple** (orden: regresión logística <
   árbol de decisión < random forest < gradient boosting): más fácil de explicar y de servir.

## 3. Umbral

Se elige sobre **validación**, solo para el modelo ya seleccionado, minimizando el costo esperado por solicitud:

```
costo(umbral) = (5 · FN + 1 · FP) / n
```

- **FN** (aprobar a quien incumplirá): costo 5. Se pierde buena parte del capital prestado.
- **FP** (rechazar a quien habría pagado): costo 1. Se pierde el margen de ese crédito.
- Costos ficticios, explícitos y acordados por el equipo. Con probabilidades bien calibradas, el umbral
  óptimo teórico es 1 / (1 + 5) ≈ 0,167; el empírico se busca en una malla de 0,01 a 0,99 (paso 0,01).

El umbral se **congela** (se escribe en `ml/seleccion/umbral_congelado.json` (versionado en Git) y en MLflow) **antes** de
evaluar la partición de prueba.

## 4. Partición de prueba

Se evalúa **una sola vez**, con el modelo seleccionado y el umbral congelado. Sus métricas se reportan en
el manifiesto y en el informe; no se usan para cambiar ninguna decisión.

## 5. Revisión de los costos (16 de noviembre de 2026, antes de usar la partición de prueba)

**Cambio:** costo de FN de **5 a 3** (FP se mantiene en 1). Umbral teórico: 1 / (1 + 3) = 0,25.

**Qué se había visto al decidirlo:** solo resultados de **validación** de la tanda `20261116T175459`.
La partición de prueba no se había evaluado con ningún modelo.

**Motivo:** con 30,6 % de incumplimiento, una razón 5:1 pone el umbral óptimo (≈ 0,17) por debajo de la
tasa base: con el mejor candidato se rechazaba el 79,8 % de las solicitudes y el costo bajaba solo 3,5 %
frente a "rechazar a todos". Un comercio que financia compras no opera rechazando 4 de cada 5 clientes.
Con 3:1 (validación, mismo modelo): rechazo 57,9 %, recall de incumplimiento 0,76, costo 19,1 % menor
que rechazar a todos.

**Qué NO cambia:** la métrica de selección (AP) y el desempate no dependen de los costos, así que el
candidato seleccionado es el mismo con cualquiera de las dos razones. Las ejecuciones de la tanda
registran `costo_fn = 5` porque se entrenaron antes de esta revisión; el umbral se elige y congela con 3:1.
