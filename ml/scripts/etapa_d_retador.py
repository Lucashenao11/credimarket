"""Prepara un modelo RETADOR (v2) a partir de un candidato ya registrado en MLflow.

Ejecutar desde la raíz del repo:
    MLFLOW_TRACKING_URI=http://localhost:5000 ml/.venv/bin/python ml/scripts/etapa_d_retador.py gradient_boosting

Igual que la selección de v1, pero para un candidato elegido a mano:
- Descarga el pipeline EXACTO del run (no se reentrena).
- Elige su umbral de costo mínimo en VALIDACIÓN, con los mismos costos (FN=3, FP=1).
- NO usa la partición de prueba: ya se usó una vez para v1 (criterio_seleccion.md §4).
Salida: ml/seleccion/retador_<candidato>.json, que exportar.py usa con --decision.
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


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    if "MLFLOW_TRACKING_URI" not in os.environ:
        print("Define MLFLOW_TRACKING_URI (p. ej. http://localhost:5000)")
        return 1
    candidato = sys.argv[1]
    tabla = pd.read_csv(SEL / "comparacion_validacion.csv").set_index("candidato")
    if candidato not in tabla.index:
        print(f"{candidato} no está en comparacion_validacion.csv: {list(tabla.index)}")
        return 1
    fila = tabla.loc[candidato]

    ruta = Path(mlflow.artifacts.download_artifacts(run_id=fila.run_id, artifact_path="pipeline.joblib",
                                                    dst_path=tempfile.mkdtemp()))
    pipe = joblib.load(ruta)
    val = cargar_particiones()["validacion"]
    p = pipe.predict_proba(val[FEATURES])[:, 1]
    costos = curva_costos(val[OBJETIVO], p)
    umbral = float(costos.loc[costos["costo"].idxmin(), "umbral"])
    m = metricas(val[OBJETIVO], p, umbral)

    decision = {
        "congelado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rol": "retador",
        "candidato": candidato, "algoritmo": fila.algoritmo, "run_id": fila.run_id, "tanda": fila.tanda,
        "pipeline_sha256": sha256_archivo(ruta),
        "umbral": umbral, "umbral_teorico": round(COSTO_FP / (COSTO_FP + COSTO_FN), 4),
        "costo_fn": COSTO_FN, "costo_fp": COSTO_FP,
        "criterio_sha256": sha256_archivo(DIR_ML / "criterio_seleccion.md"),
        "nota": "Retador elegido a mano entre los candidatos de la tanda. No fue el seleccionado por el "
                "criterio (empató en AP con v1 y perdió el desempate por Brier). Sin métricas de prueba: "
                "la partición de prueba se usó una sola vez, para v1.",
        "validacion": {"umbral": umbral, **m},
    }
    salida = SEL / f"retador_{candidato}.json"
    salida.write_text(json.dumps(decision, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    png = SEL / f"curva_costos_validacion_{candidato}.png"
    figura_costos(costos, umbral, f"{candidato} — validación (FN={COSTO_FN:g}, FP={COSTO_FP:g})", png)

    with mlflow.start_run(run_id=fila.run_id):
        mlflow.set_tags({"retador": "true"})
        mlflow.log_params({"umbral_congelado": umbral, "costo_fn_umbral": COSTO_FN,
                           "costo_fp_umbral": COSTO_FP})
        mlflow.log_metrics({f"val_congelado_{k}": v for k, v in m.items() if not isinstance(v, list)})
        mlflow.log_artifact(str(salida), artifact_path="seleccion")
        mlflow.log_artifact(str(png), artifact_path="seleccion")

    print(f"Retador {candidato} (run {fila.run_id}): umbral {umbral:.2f}, AP {m['average_precision']:.4f}, "
          f"Brier {m['brier']:.4f}, rechazo {m['tasa_rechazo']:.1%}, recall {m['recall']:.3f}, "
          f"costo {m['costo_por_solicitud']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
