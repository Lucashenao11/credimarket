"""Etapas B y C: baseline + candidatos, cada uno registrado como una ejecución de MLflow.

Ejecutar desde la raíz del repo (con MLflow arriba):
    MLFLOW_TRACKING_URI=http://localhost:5000 ml/.venv/bin/python ml/scripts/etapa_b_entrenar.py

Solo usa entrenamiento (para ajustar) y validación (para medir). La partición de prueba NO se toca aquí.
El criterio de selección está fijado de antemano en ml/criterio_seleccion.md.

Salida local versionada: ml/seleccion/comparacion_validacion.csv (una fila por ejecución, con su run_id).
"""
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import joblib
import matplotlib
import mlflow
import numpy as np
import pandas as pd
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier

matplotlib.use("Agg")
sys.path.insert(0, str(Path(__file__).parent))
from comun import (CAT, DINERO, DIR_ML, FEATURES, NUM, OBJETIVO, SEMILLA, cargar_particiones,  # noqa: E402
                   construir_preprocesador, sha256_archivo)
from metricas import (COSTO_FN, COSTO_FP, curva_costos, figura_matriz, metricas,  # noqa: E402
                      reporte_clasificacion)

EXPERIMENTO = "credimarket-riesgo-incumplimiento"
CRITERIO = DIR_ML / "criterio_seleccion.md"
SALIDA = DIR_ML / "seleccion"

# (nombre, algoritmo, estimador, opciones del preprocesador)
# Hiperparámetros elegidos a mano, pocos y razonables: el objetivo es comparar familias de modelos
# con regularización sensata, no exprimir la validación (con 2 400 filas eso sería sobreajustarla).
CANDIDATOS = [
    ("baseline_prior", "dummy", DummyClassifier(strategy="prior"), {}),
    ("logistica_c1", "logistic_regression",
     LogisticRegression(C=1.0, max_iter=2000, random_state=SEMILLA), {}),
    ("logistica_log_c1", "logistic_regression",
     LogisticRegression(C=1.0, max_iter=2000, random_state=SEMILLA), {"log_dinero": True}),
    ("logistica_log_balanceada", "logistic_regression",
     LogisticRegression(C=1.0, max_iter=2000, class_weight="balanced", random_state=SEMILLA),
     {"log_dinero": True}),
    ("arbol_p5", "decision_tree",
     DecisionTreeClassifier(max_depth=5, min_samples_leaf=50, random_state=SEMILLA), {"escalar": False}),
    ("arbol_p8", "decision_tree",
     DecisionTreeClassifier(max_depth=8, min_samples_leaf=100, random_state=SEMILLA), {"escalar": False}),
    ("random_forest_300", "random_forest",
     RandomForestClassifier(n_estimators=300, min_samples_leaf=20, max_features="sqrt", n_jobs=-1,
                            random_state=SEMILLA), {"escalar": False}),
    ("random_forest_500_p12", "random_forest",
     RandomForestClassifier(n_estimators=500, max_depth=12, min_samples_leaf=10, max_features="sqrt",
                            n_jobs=-1, random_state=SEMILLA), {"escalar": False}),
    ("gradient_boosting", "hist_gradient_boosting",
     HistGradientBoostingClassifier(learning_rate=0.05, max_iter=300, max_leaf_nodes=15,
                                    min_samples_leaf=50, l2_regularization=1.0, early_stopping=False,
                                    random_state=SEMILLA), {"escalar": False}),
]


def git(*args) -> str:
    try:
        return subprocess.run(["git", *args], cwd=DIR_ML.parent, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "desconocido"


def main() -> int:
    if "MLFLOW_TRACKING_URI" not in os.environ:
        print("Define MLFLOW_TRACKING_URI (p. ej. http://localhost:5000)")
        return 1
    meta = json.loads((DIR_ML / "data/particiones_meta.json").read_text(encoding="utf-8"))
    sha_csv = sha256_archivo(DIR_ML / "data/prestamos_entrenamiento.csv")
    if sha_csv != meta["dataset_sha256"]:
        print("El CSV cambió desde la etapa A: vuelve a ejecutar etapa_a_datos.py")
        return 1
    part = cargar_particiones()
    X_ent, y_ent = part["entrenamiento"][FEATURES], part["entrenamiento"][OBJETIVO]
    X_val, y_val = part["validacion"][FEATURES], part["validacion"][OBJETIVO]

    commit = git("rev-parse", "HEAD")
    sucio = bool(git("status", "--porcelain", "--", "ml/"))
    criterio_sha = sha256_archivo(CRITERIO)
    dependencias = {"python": platform.python_version(), "scikit-learn": sklearn.__version__,
                    "pandas": pd.__version__, "numpy": np.__version__, "joblib": joblib.__version__,
                    "mlflow": mlflow.__version__}
    tanda = time.strftime("%Y%m%dT%H%M%S")

    mlflow.set_experiment(EXPERIMENTO)
    filas = []
    for nombre, algoritmo, estimador, opciones_pre in CANDIDATOS:
        pre = construir_preprocesador(**opciones_pre)
        pipe = Pipeline([("pre", pre), ("clf", estimador)])
        with mlflow.start_run(run_name=nombre) as run:
            t0 = time.perf_counter()
            pipe.fit(X_ent, y_ent)
            duracion = time.perf_counter() - t0
            p_val = pipe.predict_proba(X_val)[:, 1]
            p_ent = pipe.predict_proba(X_ent)[:, 1]
            m_05 = metricas(y_val, p_val, 0.5)
            costos = curva_costos(y_val, p_val)
            u_opt = float(costos.loc[costos["costo"].idxmin(), "umbral"])
            m_opt = metricas(y_val, p_val, u_opt)
            m_ent = metricas(y_ent, p_ent, 0.5)

            mlflow.set_tags({
                "etapa": "B", "tanda": tanda, "algoritmo": algoritmo,
                "git_commit": commit, "git_arbol_sucio": str(sucio),
                "criterio_sha256": criterio_sha,
                "metrica_seleccion": "average_precision en validacion",
            })
            params = {"algoritmo": algoritmo, "semilla": SEMILLA,
                      "estrategia_particion": meta["estrategia"],
                      "particion_tamanos": json.dumps(meta["tamanos"]),
                      "dataset_version": meta["dataset_version"], "dataset_sha256": sha_csv,
                      "particiones_sha256": meta["particiones_sha256"],
                      "features": json.dumps(FEATURES), "n_features": len(FEATURES),
                      "pre_numericas": "mediana + indicador de faltante" +
                                       (" + StandardScaler" if opciones_pre.get("escalar", True) else ""),
                      "pre_log_dinero": json.dumps(DINERO) if opciones_pre.get("log_dinero") else "no",
                      "pre_categoricas": f"{CAT}: NaN/None -> 'desconocido' + OneHot(ignore)",
                      "costo_fn": COSTO_FN, "costo_fp": COSTO_FP,
                      **{f"dep_{k}": v for k, v in dependencias.items()}}
            params.update({f"hp_{k}": v for k, v in estimador.get_params().items()
                           if isinstance(v, (int, float, str, bool, type(None)))})
            mlflow.log_params(params)
            mlflow.log_metric("duracion_entrenamiento_s", duracion)
            mlflow.log_metrics({f"val_{k}": v for k, v in m_05.items() if not isinstance(v, list)})
            mlflow.log_metrics({f"val_opt_{k}": v for k, v in m_opt.items() if not isinstance(v, list)})
            mlflow.log_metric("val_umbral_costo_minimo", u_opt)
            mlflow.log_metrics({"ent_roc_auc": m_ent["roc_auc"],
                                "ent_average_precision": m_ent["average_precision"],
                                "ent_brier": m_ent["brier"]})

            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                joblib.dump(pipe, tmp / "pipeline.joblib")
                figura_matriz(m_05["matriz_confusion"], f"{nombre} — validación, umbral 0,50",
                              tmp / "matriz_confusion_val_u050.png")
                figura_matriz(m_opt["matriz_confusion"], f"{nombre} — validación, umbral {u_opt:.2f}",
                              tmp / "matriz_confusion_val_costo_min.png")
                (tmp / "reporte_validacion.txt").write_text(
                    reporte_clasificacion(y_val, p_val, 0.5, u_opt), encoding="utf-8")
                (tmp / "metricas_validacion.json").write_text(json.dumps(
                    {"umbral_050": m_05, "umbral_costo_minimo": {"umbral": u_opt, **m_opt},
                     "entrenamiento_umbral_050": m_ent}, indent=2), encoding="utf-8")
                costos.to_csv(tmp / "curva_costos_validacion.csv", index=False)
                (tmp / "dependencias.json").write_text(json.dumps(dependencias, indent=2), encoding="utf-8")
                mlflow.log_artifacts(tmp)
            # El código exacto que produjo la ejecución (el árbol puede tener cambios sin commit)
            for archivo in ["scripts/comun.py", "scripts/metricas.py", "scripts/etapa_b_entrenar.py",
                            "requirements.txt", "criterio_seleccion.md"]:
                mlflow.log_artifact(str(DIR_ML / archivo), artifact_path="codigo")

        filas.append({"candidato": nombre, "algoritmo": algoritmo, "run_id": run.info.run_id,
                      "val_average_precision": m_05["average_precision"], "val_roc_auc": m_05["roc_auc"],
                      "val_brier": m_05["brier"], "val_precision_u050": m_05["precision"],
                      "val_recall_u050": m_05["recall"], "val_f1_u050": m_05["f1"],
                      "val_umbral_costo_min": u_opt, "val_costo_min": m_opt["costo_por_solicitud"],
                      "ent_average_precision": m_ent["average_precision"],
                      "duracion_s": round(duracion, 2)})
        print(f"{nombre:28s} AP={m_05['average_precision']:.4f} AUC={m_05['roc_auc']:.4f} "
              f"Brier={m_05['brier']:.4f} costo_min={m_opt['costo_por_solicitud']:.4f}@{u_opt:.2f} "
              f"(AP ent {m_ent['average_precision']:.4f}, {duracion:.1f}s)")

    SALIDA.mkdir(exist_ok=True)
    tabla = pd.DataFrame(filas).round(4)
    tabla.insert(0, "tanda", tanda)
    tabla.to_csv(SALIDA / "comparacion_validacion.csv", index=False, lineterminator="\n")
    print(f"\nTanda {tanda}: {len(filas)} ejecuciones en '{EXPERIMENTO}' (commit {commit[:7]}, "
          f"árbol {'con' if sucio else 'sin'} cambios sin commit)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
