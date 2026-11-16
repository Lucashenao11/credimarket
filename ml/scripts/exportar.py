"""Etapa D: exporta una versión a ml/registry/<version>/ según el contrato 4.3.

Ejecutar desde la raíz del repo:
    MLFLOW_TRACKING_URI=http://localhost:5000 ml/.venv/bin/python ml/scripts/exportar.py v1

Copia el pipeline.joblib EXACTO de la ejecución de MLflow (mismo SHA-256 que el artefacto del run),
escribe manifest.json, ejemplo_entrada.json y ejemplo_salida.json. NO promueve: eso lo hace promover.py.
"""
import argparse
import json
import math
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import joblib
import mlflow
import numpy as np
import pandas as pd
import sklearn

sys.path.insert(0, str(Path(__file__).parent))
from comun import (DIR_ML, EXCLUIDAS, FEATURES, ID, TIPOS, cargar_particiones,  # noqa: E402
                   sha256_archivo)

REGISTRO = DIR_ML / "registry"
SEL = DIR_ML / "seleccion"
CLAVES_PLANAS = ["average_precision", "roc_auc", "brier", "precision", "recall", "f1", "tasa_rechazo",
                 "costo_por_solicitud"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("version", help="p. ej. v1")
    ap.add_argument("--decision", default=str(SEL / "umbral_congelado.json"),
                    help="JSON con run_id y umbral (v1: umbral_congelado.json; v2: retador_<candidato>.json)")
    ap.add_argument("--forzar", action="store_true", help="sobrescribir si la carpeta ya existe")
    args = ap.parse_args()
    if "MLFLOW_TRACKING_URI" not in os.environ:
        print("Define MLFLOW_TRACKING_URI (p. ej. http://localhost:5000)")
        return 1
    destino = REGISTRO / args.version
    if destino.exists() and not args.forzar:
        print(f"{destino} ya existe. Una versión publicada no se modifica (usa otra versión).")
        return 1

    congelado = json.loads(Path(args.decision).read_text(encoding="utf-8"))
    meta = json.loads((DIR_ML / "data/particiones_meta.json").read_text(encoding="utf-8"))
    # Métricas de prueba solo si la evaluación única corresponde a ESTE run (v1). Un retador no tiene.
    ruta_prueba = SEL / "evaluacion_prueba.json"
    prueba = json.loads(ruta_prueba.read_text(encoding="utf-8")) if ruta_prueba.exists() else None
    if prueba and prueba["run_id"] != congelado["run_id"]:
        prueba = None
    if prueba is None and congelado.get("rol") != "retador":
        print("El modelo seleccionado debe tener su evaluación de prueba (evaluar_prueba.py).")
        return 1

    tmp = Path(tempfile.mkdtemp())
    origen = Path(mlflow.artifacts.download_artifacts(run_id=congelado["run_id"],
                                                      artifact_path="pipeline.joblib", dst_path=str(tmp)))
    if sha256_archivo(origen) != congelado["pipeline_sha256"]:
        print("El pipeline de MLflow no coincide con el congelado.")
        return 1
    destino.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origen, destino / "pipeline.joblib")
    pipe = joblib.load(destino / "pipeline.joblib")
    run = mlflow.get_run(congelado["run_id"])

    # Ejemplo: la primera solicitud (por id) de la partición de prueba, tal como la recibiría Préstamos
    fila = cargar_particiones()["prueba"].sort_values(ID).iloc[[0]]
    entrada = {k: (None if isinstance(v, float) and math.isnan(v) else v)
               for k, v in json.loads(fila[FEATURES].to_json(orient="records"))[0].items()}
    p = float(pipe.predict_proba(pd.DataFrame([entrada])[FEATURES])[0, 1])
    salida = {"probabilidad_incumplimiento": p, "umbral": congelado["umbral"],
              "decision": "RIESGO_ALTO" if p >= congelado["umbral"] else "FAVORABLE",
              "model_version": args.version}

    v = congelado["validacion"]
    t = prueba["prueba"] if prueba else None
    manifiesto = {
        "model_version": args.version,
        "run_id": congelado["run_id"],
        "mlflow_experimento": mlflow.get_experiment(run.info.experiment_id).name,
        "candidato": congelado["candidato"],
        "algoritmo": congelado["algoritmo"],
        "rol": congelado.get("rol", "seleccionado"),
        "creado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": run.data.tags.get("git_commit"),
        "dataset_version": meta["dataset_version"],
        "dataset_sha256": meta["dataset_sha256"],
        "particiones_sha256": meta["particiones_sha256"],
        "particion": meta["estrategia"] + f", semilla {meta['semilla']}",
        "features": [{"nombre": f, "tipo": TIPOS[f]} for f in FEATURES],
        "excluidas": EXCLUIDAS,
        "clase_positiva": 1,
        "clase_positiva_significado": "incumplimiento a 90 días",
        "salida": "pipeline.predict_proba(df)[:, 1] = probabilidad de incumplimiento",
        "umbral": congelado["umbral"],
        "umbral_criterio": {"costo_fn": congelado["costo_fn"], "costo_fp": congelado["costo_fp"],
                            "elegido_en": "validacion", "congelado_en": congelado["congelado_en"]},
        # Plano y numérico: el frontend (admin/modelo) lo muestra como clave: valor
        "metricas": {**{f"validacion_{k}": round(v[k], 4) for k in CLAVES_PLANAS},
                     **({f"prueba_{k}": round(t[k], 4) for k in CLAVES_PLANAS} if t else {})},
        "metricas_prueba_nota": ("Evaluación única de la partición de prueba." if t else
                                 "Sin métricas de prueba: la partición de prueba se usó una sola vez, "
                                 "para el modelo seleccionado (v1)."),
        "matrices_confusion": {"validacion": v["matriz_confusion"],
                               "prueba": t["matriz_confusion"] if t else None,
                               "formato": "[[tn, fp], [fn, tp]] con el umbral del manifiesto"},
        "dependencias": {"scikit-learn": sklearn.__version__, "pandas": pd.__version__,
                         "numpy": np.__version__, "joblib": joblib.__version__},
        "artefacto_sha256": sha256_archivo(destino / "pipeline.joblib"),
    }
    escribir = lambda nombre, obj: (destino / nombre).write_text(  # noqa: E731
        json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    escribir("manifest.json", manifiesto)
    escribir("ejemplo_entrada.json", entrada)
    escribir("ejemplo_salida.json", salida)

    with mlflow.start_run(run_id=congelado["run_id"]):
        mlflow.set_tag(f"exportado_{args.version}", manifiesto["creado_en"])
        mlflow.log_artifact(str(destino / "manifest.json"), artifact_path=f"export_{args.version}")

    print(f"Exportado {destino} (no promovido)")
    print(f"  artefacto_sha256 {manifiesto['artefacto_sha256']}")
    print(f"  ejemplo: p={p:.6f} -> {salida['decision']} (umbral {congelado['umbral']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
