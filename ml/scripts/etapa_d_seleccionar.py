"""Selección del candidato y congelamiento del umbral (solo con VALIDACIÓN).

Ejecutar desde la raíz del repo:
    MLFLOW_TRACKING_URI=http://localhost:5000 ml/.venv/bin/python ml/scripts/etapa_d_seleccionar.py

1. Aplica el criterio de ml/criterio_seleccion.md a ml/seleccion/comparacion_validacion.csv.
2. Descarga de MLflow el pipeline EXACTO de la ejecución ganadora (no se reentrena).
3. Elige el umbral de costo mínimo en validación y lo congela en ml/seleccion/umbral_congelado.json.

Se niega a correr si la prueba ya se evaluó: el umbral no puede elegirse después de mirarla.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import joblib
import mlflow
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from comun import DIR_ML, FEATURES, OBJETIVO, cargar_particiones, sha256_archivo  # noqa: E402
from metricas import COSTO_FN, COSTO_FP, curva_costos, figura_costos, metricas  # noqa: E402

SEL = DIR_ML / "seleccion"
MARGEN_AP = 0.005
MARGEN_BRIER = 0.002
SIMPLICIDAD = {"logistic_regression": 0, "decision_tree": 1, "random_forest": 2,
               "hist_gradient_boosting": 3}


def aplicar_criterio(tabla: pd.DataFrame) -> tuple[pd.Series, list[str]]:
    """Devuelve el candidato ganador y la traza de la decisión, paso a paso."""
    t = tabla[tabla["algoritmo"] != "dummy"].copy()
    traza = []
    mejor_ap = t["val_average_precision"].max()
    empatados = t[t["val_average_precision"] >= mejor_ap - MARGEN_AP]
    traza.append(f"1. Mejor AP en validación: {mejor_ap:.4f}. Dentro de {MARGEN_AP} quedan: "
                 + ", ".join(f"{r.candidato} ({r.val_average_precision:.4f})" for r in empatados.itertuples()))
    if len(empatados) == 1:
        return empatados.iloc[0], traza
    mejor_brier = empatados["val_brier"].min()
    empatados = empatados[empatados["val_brier"] <= mejor_brier + MARGEN_BRIER]
    traza.append(f"2. Desempate por Brier (mejor {mejor_brier:.4f}, margen {MARGEN_BRIER}): quedan "
                 + ", ".join(f"{r.candidato} ({r.val_brier:.4f})" for r in empatados.itertuples()))
    if len(empatados) == 1:
        return empatados.iloc[0], traza
    empatados = empatados.assign(_s=empatados["algoritmo"].map(SIMPLICIDAD)).sort_values("_s")
    traza.append(f"3. Desempate por simplicidad: gana {empatados.iloc[0].candidato}")
    return empatados.iloc[0], traza


def main() -> int:
    if "MLFLOW_TRACKING_URI" not in os.environ:
        print("Define MLFLOW_TRACKING_URI (p. ej. http://localhost:5000)")
        return 1
    if (SEL / "evaluacion_prueba.json").exists():
        print("La partición de prueba ya se evaluó: el umbral no se puede volver a elegir.")
        return 1

    tabla = pd.read_csv(SEL / "comparacion_validacion.csv")
    ganador, traza = aplicar_criterio(tabla)
    for linea in traza:
        print(linea)

    dst = Path(tempfile.mkdtemp())
    ruta = Path(mlflow.artifacts.download_artifacts(run_id=ganador.run_id, artifact_path="pipeline.joblib",
                                                    dst_path=str(dst)))
    pipe = joblib.load(ruta)
    val = cargar_particiones()["validacion"]
    p = pipe.predict_proba(val[FEATURES])[:, 1]
    costos = curva_costos(val[OBJETIVO], p)
    fila = costos.loc[costos["costo"].idxmin()]
    umbral = float(fila["umbral"])
    m = metricas(val[OBJETIVO], p, umbral)

    congelado = {
        "congelado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "candidato": ganador.candidato, "algoritmo": ganador.algoritmo, "run_id": ganador.run_id,
        "tanda": ganador.tanda, "pipeline_sha256": sha256_archivo(ruta),
        "umbral": umbral, "umbral_teorico": round(COSTO_FP / (COSTO_FP + COSTO_FN), 4),
        "costo_fn": COSTO_FN, "costo_fp": COSTO_FP,
        "criterio_sha256": sha256_archivo(DIR_ML / "criterio_seleccion.md"),
        "traza_seleccion": traza,
        "validacion": {"umbral": umbral, **m},
    }
    SEL.mkdir(exist_ok=True)
    (SEL / "umbral_congelado.json").write_text(json.dumps(congelado, indent=2, ensure_ascii=False) + "\n",
                                               encoding="utf-8")
    costos.to_csv(SEL / "curva_costos_validacion.csv", index=False, lineterminator="\n")
    figura_costos(costos, umbral, f"{ganador.candidato} — validación (FN={COSTO_FN:g}, FP={COSTO_FP:g})",
                  SEL / "curva_costos_validacion.png")

    # Queda también en la ejecución ganadora de MLflow
    with mlflow.start_run(run_id=ganador.run_id):
        mlflow.set_tags({"seleccionado": "true", "criterio_sha256_seleccion": congelado["criterio_sha256"]})
        mlflow.log_params({"umbral_congelado": umbral, "costo_fn_umbral": COSTO_FN, "costo_fp_umbral": COSTO_FP})
        mlflow.log_metrics({f"val_congelado_{k}": v for k, v in m.items() if not isinstance(v, list)})
        for nombre in ["umbral_congelado.json", "curva_costos_validacion.csv", "curva_costos_validacion.png"]:
            mlflow.log_artifact(str(SEL / nombre), artifact_path="seleccion")

    print(f"\nSeleccionado: {ganador.candidato} (run {ganador.run_id})")
    print(f"Umbral congelado: {umbral:.2f} (teórico {congelado['umbral_teorico']}), costo "
          f"{m['costo_por_solicitud']:.4f}, rechazo {m['tasa_rechazo']:.1%}, recall {m['recall']:.3f}, "
          f"precisión {m['precision']:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
