"""Evaluación ÚNICA de la partición de prueba con el modelo y el umbral congelados.

Ejecutar desde la raíz del repo:
    MLFLOW_TRACKING_URI=http://localhost:5000 ml/.venv/bin/python ml/scripts/evaluar_prueba.py

Garantías:
- Exige ml/seleccion/umbral_congelado.json (el umbral se eligió antes, solo con validación).
- Verifica que el pipeline descargado de MLflow tenga el mismo SHA-256 que se congeló.
- Se niega a correr si ml/seleccion/evaluacion_prueba.json ya existe: la prueba se usa una sola vez.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import joblib
import mlflow

sys.path.insert(0, str(Path(__file__).parent))
from comun import DIR_ML, FEATURES, OBJETIVO, cargar_particiones, sha256_archivo  # noqa: E402
from metricas import figura_matriz, metricas, reporte_clasificacion  # noqa: E402

SEL = DIR_ML / "seleccion"


def main() -> int:
    if "MLFLOW_TRACKING_URI" not in os.environ:
        print("Define MLFLOW_TRACKING_URI (p. ej. http://localhost:5000)")
        return 1
    salida = SEL / "evaluacion_prueba.json"
    if salida.exists():
        print(f"{salida} ya existe: la partición de prueba ya se usó. No se vuelve a evaluar.")
        return 1
    congelado = json.loads((SEL / "umbral_congelado.json").read_text(encoding="utf-8"))
    ruta = Path(mlflow.artifacts.download_artifacts(run_id=congelado["run_id"], artifact_path="pipeline.joblib",
                                                    dst_path=tempfile.mkdtemp()))
    if sha256_archivo(ruta) != congelado["pipeline_sha256"]:
        print("El pipeline de MLflow no coincide con el congelado.")
        return 1
    pipe = joblib.load(ruta)
    prueba = cargar_particiones()["prueba"]
    p = pipe.predict_proba(prueba[FEATURES])[:, 1]
    u = congelado["umbral"]
    m = metricas(prueba[OBJETIVO], p, u)

    resultado = {"evaluado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "run_id": congelado["run_id"], "candidato": congelado["candidato"],
                 "pipeline_sha256": congelado["pipeline_sha256"], "n": len(prueba),
                 "prueba": {"umbral": u, **m}}
    salida.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    figura_matriz(m["matriz_confusion"], f"{congelado['candidato']} — PRUEBA, umbral {u:.2f}",
                  SEL / "matriz_confusion_prueba.png")
    (SEL / "reporte_prueba.txt").write_text(reporte_clasificacion(prueba[OBJETIVO], p, u), encoding="utf-8")

    with mlflow.start_run(run_id=congelado["run_id"]):
        mlflow.log_metrics({f"prueba_{k}": v for k, v in m.items() if not isinstance(v, list)})
        for nombre in ["evaluacion_prueba.json", "matriz_confusion_prueba.png", "reporte_prueba.txt"]:
            mlflow.log_artifact(str(SEL / nombre), artifact_path="prueba")

    v = congelado["validacion"]
    print(f"{'métrica':22s} {'validación':>11s} {'prueba':>9s}")
    for k in ["average_precision", "roc_auc", "brier", "precision", "recall", "f1", "tasa_rechazo",
              "costo_por_solicitud"]:
        print(f"{k:22s} {v[k]:11.4f} {m[k]:9.4f}")
    print("matriz de confusión prueba [[tn, fp], [fn, tp]]:", m["matriz_confusion"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
