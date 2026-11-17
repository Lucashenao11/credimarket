"""Etapa F: monitoreo y drift simulado con PSI (Population Stability Index).

Ejecutar desde la raíz del repo:
    MLFLOW_TRACKING_URI=http://localhost:5000 ml/.venv/bin/python ml/scripts/etapa_f_drift.py

Referencia: la partición de ENTRENAMIENTO (lo que vio el modelo). Actual: ml/data/solicitudes_nuevas.csv.

PSI = Σ (a_i − r_i) · ln(a_i / r_i), con r_i y a_i las proporciones de referencia y actuales en el grupo i.
- Numéricas: 10 grupos por deciles de la referencia (los bordes se fijan con la referencia y se aplican
  igual a los datos nuevos). Discretas con pocos valores (plazo) y tipo_empleo: un grupo por valor.
- Faltante = grupo propio: si cambia la tasa de faltantes, eso también es drift.
- Proporción 0 se reemplaza por 1e-4 para que el logaritmo exista.
Umbrales usuales: < 0,10 estable; 0,10–0,25 cambio moderado (vigilar); > 0,25 cambio significativo.

Ruido de muestreo: con solo 200 solicitudes nuevas, el PSI es > 0 aunque no haya drift. Se estima con
1 000 muestras de 200 filas de VALIDACIÓN (misma distribución que entrenamiento): su percentil 95 es el
PSI que se puede obtener por azar. Una variable se marca solo si supera el umbral Y ese percentil.

Además: escenario SINTÉTICO de drift inducido para comprobar la sensibilidad del monitor.

Salidas: ml/reporte_drift.md, ml/drift/psi_por_variable.csv, ml/drift/psi_escenario_inducido.csv, ml/drift/psi_por_variable.png, un run de MLflow.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib
import mlflow
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from comun import (CAT, CSV_NUEVAS, DIR_ML, FEATURES, SEMILLA, cargar_particiones,  # noqa: E402
                   sha256_archivo)

SALIDA = DIR_ML / "drift"
POR_VALOR = CAT + ["plazo_meses"]
N_GRUPOS = 10
EPS = 1e-4
REPETICIONES = 1000
ESTABLE, MODERADO = 0.10, 0.25
FALTANTE = "(faltante)"


def grupos_referencia(ref: pd.Series, por_valor: bool):
    if por_valor:
        return sorted(ref.dropna().unique().tolist())
    bordes = np.unique(np.quantile(ref.dropna(), np.linspace(0, 1, N_GRUPOS + 1)))
    bordes[0], bordes[-1] = -np.inf, np.inf  # valores nuevos fuera del rango caen en los extremos
    return bordes


def proporciones(s: pd.Series, grupos, por_valor: bool) -> pd.Series:
    if por_valor:
        etiquetas = s.where(s.isin(grupos), "(otro)").where(s.notna(), FALTANTE)
        orden = list(grupos) + ["(otro)", FALTANTE]
    else:
        # Se agrupa por el NÚMERO de grupo (no por el texto del intervalo: pd.cut redondea sus etiquetas
        # y no coincidirían con los bordes exactos). Grupo i = (bordes[i], bordes[i+1]].
        orden = [f"({_f(grupos[i])}, {_f(grupos[i + 1])}]" for i in range(len(grupos) - 1)] + [FALTANTE]
        codigos = np.searchsorted(grupos, s.to_numpy(dtype=float), side="left") - 1
        codigos = np.clip(codigos, 0, len(grupos) - 2)
        etiquetas = pd.Series(np.array(orden, dtype=object)[codigos], index=s.index).where(s.notna(), FALTANTE)
    return etiquetas.value_counts(normalize=True).reindex(orden, fill_value=0.0)


def _f(x: float) -> str:
    return "∞" if np.isposinf(x) else ("−∞" if np.isneginf(x) else f"{x:,.4g}")


def psi(r: pd.Series, a: pd.Series) -> float:
    r, a = np.clip(r.values, EPS, None), np.clip(a.values, EPS, None)
    return float(np.sum((a - r) * np.log(a / r)))


def psi_columna(ref: pd.Series, act: pd.Series, por_valor: bool) -> tuple[float, pd.DataFrame]:
    g = grupos_referencia(ref, por_valor)
    r, a = proporciones(ref, g, por_valor), proporciones(act, g, por_valor)
    detalle = pd.DataFrame({"referencia": r, "actual": a})
    detalle = detalle[(detalle["referencia"] > 0) | (detalle["actual"] > 0)]
    return psi(r, a), detalle


def nivel(valor: float) -> str:
    return "estable" if valor < ESTABLE else ("moderado" if valor <= MODERADO else "significativo")


def tabla_psi(ref, actual, columnas, ruido) -> tuple[pd.DataFrame, dict]:
    """PSI de cada columna entre ref y actual, con su ruido p95 y la marca de alerta."""
    filas, detalles = [], {}
    for c in columnas:
        valor, det = psi_columna(ref[c], actual[c], c in POR_VALOR)
        p95 = float(np.percentile(ruido[c], 95))
        detalles[c] = det
        es_num = c not in CAT
        filas.append({
            "variable": c, "psi": round(valor, 4), "nivel": nivel(valor),
            "ruido_p95": round(p95, 4), "alerta": bool(valor > ESTABLE and valor > p95),
            "media_referencia": round(float(ref[c].mean()), 4) if es_num else None,
            "media_actual": round(float(actual[c].mean()), 4) if es_num else None,
            "faltantes_referencia": round(float(ref[c].isna().mean()), 4),
            "faltantes_actual": round(float(actual[c].isna().mean()), 4),
        })
    return pd.DataFrame(filas).sort_values("psi", ascending=False).reset_index(drop=True), detalles


def escenario_inducido(nuevas: pd.DataFrame, rng) -> pd.DataFrame:
    """SINTÉTICO, solo para comprobar la sensibilidad del monitor (no son datos reales):
    ingresos -20 % (p. ej. una recesión) y 30 % de los dependientes pasan a temporales."""
    d = nuevas[FEATURES].copy()
    d["ingresos_mensuales_cop"] = (d["ingresos_mensuales_cop"] * 0.8).round(-3)
    dep = d.index[d["tipo_empleo"] == "dependiente"]
    d.loc[rng.choice(dep, size=int(len(dep) * 0.3), replace=False), "tipo_empleo"] = "temporal"
    return d


def main() -> int:
    part = cargar_particiones()
    ref = part["entrenamiento"]
    val = part["validacion"]
    nuevas = pd.read_csv(CSV_NUEVAS)
    n = len(nuevas)

    activo = json.loads((DIR_ML / "registry/active.json").read_text(encoding="utf-8"))
    version = activo["model_version"]
    pipe = joblib.load(DIR_ML / "registry" / version / "pipeline.joblib")
    ref = ref.assign(score=pipe.predict_proba(ref[FEATURES])[:, 1])
    val = val.assign(score=pipe.predict_proba(val[FEATURES])[:, 1])
    nuevas = nuevas.assign(score=pipe.predict_proba(nuevas[FEATURES])[:, 1])
    columnas = FEATURES + ["score"]

    # Ruido: PSI de muestras de n filas sin drift (validación) contra la misma referencia
    rng = np.random.default_rng(SEMILLA)
    grupos = {c: grupos_referencia(ref[c], c in POR_VALOR) for c in columnas}
    props_ref = {c: proporciones(ref[c], grupos[c], c in POR_VALOR) for c in columnas}
    ruido = {c: [] for c in columnas}
    for _ in range(REPETICIONES):
        muestra = val.iloc[rng.choice(len(val), size=n, replace=False)]
        for c in columnas:
            ruido[c].append(psi(props_ref[c], proporciones(muestra[c], grupos[c], c in POR_VALOR)))

    tabla, detalles = tabla_psi(ref, nuevas, columnas, ruido)

    SALIDA.mkdir(exist_ok=True)
    tabla.to_csv(SALIDA / "psi_por_variable.csv", index=False, lineterminator="\n")
    fig, ax = plt.subplots(figsize=(7, 4.5))
    t = tabla.iloc[::-1]
    ax.barh(t["variable"], t["psi"], color=["#c0392b" if a else "#7f8c8d" for a in t["alerta"]])
    ax.scatter(t["ruido_p95"], t["variable"], marker="|", s=200, color="black", label="ruido p95 (n=200)")
    ax.axvline(ESTABLE, linestyle="--", color="#e67e22", label="0,10 (vigilar)")
    ax.axvline(MODERADO, linestyle="--", color="#c0392b", label="0,25 (significativo)")
    ax.set_xlabel("PSI: solicitudes nuevas vs. entrenamiento")
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(SALIDA / "psi_por_variable.png", dpi=120)
    plt.close(fig)

    alertas = tabla[tabla["alerta"]]
    tasa_ref = float((ref["score"] >= pipe_umbral(version)).mean())
    tasa_new = float((nuevas["score"] >= pipe_umbral(version)).mean())
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    inducido = escenario_inducido(nuevas, np.random.default_rng(SEMILLA + 1))
    inducido = inducido.assign(score=pipe.predict_proba(inducido[FEATURES])[:, 1])
    tabla_ind, _ = tabla_psi(ref, inducido, columnas, ruido)
    tabla_ind.to_csv(SALIDA / "psi_escenario_inducido.csv", index=False, lineterminator="\n")
    tasa_ind = float((inducido["score"] >= pipe_umbral(version)).mean())

    def fmt(x):
        return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:,.4g}"

    r = [
        "# Etapa F — Monitoreo y drift simulado (PSI)", "",
        f"Generado por `ml/scripts/etapa_f_drift.py` el {ahora}. No editar a mano.", "",
        "## Qué se compara", "",
        f"- **Referencia:** partición de entrenamiento ({len(ref):,} filas), la distribución que vio el modelo.",
        f"- **Actual:** `ml/data/{CSV_NUEVAS.name}` ({n} solicitudes, SHA-256 `{sha256_archivo(CSV_NUEVAS)}`).",
        f"- **Modelo para el score:** versión activa `{version}` (umbral {pipe_umbral(version)}).", "",
        "PSI = Σ (actual − referencia) · ln(actual / referencia) sobre grupos fijados con la referencia "
        f"(deciles para numéricas; un grupo por valor para {', '.join(POR_VALOR)}; los faltantes, grupo propio). "
        "Umbrales usuales: < 0,10 estable; 0,10–0,25 moderado; > 0,25 significativo.", "",
        f"**Ruido de muestreo.** Con {n} solicitudes el PSI nunca es 0 aunque no haya drift. Se tomaron "
        f"{REPETICIONES} muestras de {n} filas de *validación* (sin drift) y se calculó su PSI contra la misma "
        "referencia: la columna *ruido p95* es el PSI que el azar alcanza el 5 % de las veces. Una variable "
        "queda en **alerta** solo si supera 0,10 **y** su ruido p95.", "",
        "## Resultado", "",
        "| Variable | PSI | Nivel | Ruido p95 | Alerta | Media ref. | Media nueva | Falt. ref. | Falt. nueva |",
        "|---|---|---|---|---|---|---|---|---|",
        *[f"| `{f.variable}` | {f.psi:.4f} | {f.nivel} | {f.ruido_p95:.4f} | {'**sí**' if f.alerta else 'no'} | "
          f"{fmt(f.media_referencia)} | {fmt(f.media_actual)} | {f.faltantes_referencia:.1%} | "
          f"{f.faltantes_actual:.1%} |" for f in tabla.itertuples()],
        "", "![PSI por variable](drift/psi_por_variable.png)", "",
        f"`score` es la probabilidad de incumplimiento de `{version}`. Con el umbral activo, la tasa de "
        f"rechazo sería {tasa_new:.1%} en las solicitudes nuevas frente a {tasa_ref:.1%} en entrenamiento.", "",
        "## Lectura", "",
    ]
    if alertas.empty:
        r += ["Ninguna variable supera a la vez el umbral de 0,10 y el ruido de muestreo: **no hay evidencia "
              "de drift** con estas 200 solicitudes. Los valores de PSI observados son compatibles con el azar."]
    else:
        r += [f"Variables en alerta: {', '.join(f'`{v}`' for v in alertas['variable'])}. Detalle por grupo:", ""]
        for v in alertas["variable"]:
            d = detalles[v].copy()
            d["contribucion_psi"] = ((np.clip(d["actual"], EPS, None) - np.clip(d["referencia"], EPS, None))
                                     * np.log(np.clip(d["actual"], EPS, None) / np.clip(d["referencia"], EPS, None)))
            r += [f"**{v}**", "", "| Grupo | Referencia | Actual | Aporte al PSI |", "|---|---|---|---|",
                  *[f"| {g} | {x.referencia:.1%} | {x.actual:.1%} | {x.contribucion_psi:.4f} |"
                    for g, x in d.iterrows()], ""]
    ind_alerta = tabla_ind[tabla_ind["alerta"]]
    r += ["", "## Escenario de drift inducido (sintético)", "",
          "Para comprobar que el monitor **sí detecta** un cambio cuando existe, se alteraron a propósito las "
          "mismas 200 solicitudes nuevas: ingresos −20 % (como en una recesión) y 30 % de los dependientes "
          "pasan a temporales. **Son datos sintéticos, solo para esta prueba de sensibilidad**; no se usan "
          "para entrenar ni se presentan como solicitudes reales.", "",
          "| Variable | PSI real | PSI inducido | Ruido p95 | Alerta inducido |", "|---|---|---|---|---|",
          *[f"| `{f.variable}` | {tabla.set_index('variable').loc[f.variable, 'psi']:.4f} | {f.psi:.4f} | "
            f"{f.ruido_p95:.4f} | {'**sí**' if f.alerta else 'no'} |" for f in tabla_ind.itertuples()],
          "",
          f"Variables en alerta: {', '.join(f'`{v}`' for v in ind_alerta['variable']) or 'ninguna'}. "
          f"Con el umbral activo, el rechazo pasaría de {tasa_new:.1%} a {tasa_ind:.1%}. Las variables "
          "que no se tocaron siguen con el mismo PSI: el monitor señala exactamente dónde está el cambio.",
          ]
    r += ["", "## Qué se haría en operación", "",
          "- Calcular este reporte de forma periódica (p. ej. semanal) sobre las solicitudes recibidas por Préstamos.",
          "- PSI > 0,10 por encima del ruido en una variable: revisar la fuente (cambio de producto, de canal, "
          "error de captura) antes de tocar el modelo.",
          "- PSI > 0,25 en el `score` o en varias variables importantes: reentrenar con datos recientes, "
          "exportar una versión nueva, compararla contra la activa en validación y promoverla con "
          "`promover.py` (rollback disponible).",
          "- El drift de las entradas no prueba que el modelo se degradó: para eso se necesita la etiqueta "
          "real (incumplimiento a 90 días), que llega con 3 meses de retraso.", ""]
    (DIR_ML / "reporte_drift.md").write_text("\n".join(r), encoding="utf-8")

    if "MLFLOW_TRACKING_URI" in os.environ:
        mlflow.set_experiment("credimarket-monitoreo")
        with mlflow.start_run(run_name=f"drift_{CSV_NUEVAS.stem}"):
            mlflow.set_tags({"etapa": "F", "model_version": version})
            mlflow.log_params({"referencia": "particion entrenamiento", "actual": CSV_NUEVAS.name,
                               "actual_sha256": sha256_archivo(CSV_NUEVAS), "n_actual": n,
                               "grupos": N_GRUPOS, "repeticiones_ruido": REPETICIONES, "semilla": SEMILLA})
            mlflow.log_metrics({f"psi_{f.variable}": f.psi for f in tabla.itertuples()})
            mlflow.log_metric("variables_en_alerta", int(tabla["alerta"].sum()))
            mlflow.log_metrics({f"inducido_psi_{f.variable}": f.psi for f in tabla_ind.itertuples()})
            mlflow.log_metric("inducido_variables_en_alerta", int(tabla_ind["alerta"].sum()))
            mlflow.log_artifacts(str(SALIDA), artifact_path="drift")
            mlflow.log_artifact(str(DIR_ML / "reporte_drift.md"))

    print(tabla[["variable", "psi", "nivel", "ruido_p95", "alerta"]].to_string(index=False))
    print(f"\nRechazo con {version}: nuevas {tasa_new:.1%} vs entrenamiento {tasa_ref:.1%}")
    print("\nEscenario inducido (sintético):")
    print(tabla_ind[["variable", "psi", "nivel", "ruido_p95", "alerta"]].to_string(index=False))
    print(f"Rechazo inducido: {tasa_ind:.1%}")
    return 0


def pipe_umbral(version: str) -> float:
    m = json.loads((DIR_ML / "registry" / version / "manifest.json").read_text(encoding="utf-8"))
    return float(m["umbral"])


if __name__ == "__main__":
    sys.exit(main())
