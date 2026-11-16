"""Modelo BASE para destrabar Préstamos. NO es la entrega de ML: sin MLflow, sin comparación de modelos.
TODO(compañero): etapas A-F (EDA, comparación, MLflow, selección de umbral, manifiesto completo).
Ejecutar desde la raíz del repo:  python ml/scripts/entrenar_basico.py
"""
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

import joblib, numpy as np, pandas as pd, sklearn
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

VERSION = "v0-basico"
RAIZ = Path(__file__).resolve().parents[2]
CSV = RAIZ / "ml/data/prestamos_entrenamiento.csv"
SALIDA = RAIZ / "ml/registry" / VERSION

NUM = ["ingresos_mensuales_cop", "obligaciones_mensuales_cop", "antiguedad_laboral_meses",
       "meses_historial_crediticio", "creditos_previos", "atrasos_previos_30d",
       "porcentaje_pago_puntual", "monto_solicitado_cop", "plazo_meses", "cuota_estimada_cop"]
CAT = ["tipo_empleo"]
FEATURES = ["ingresos_mensuales_cop", "obligaciones_mensuales_cop", "tipo_empleo",
            "antiguedad_laboral_meses", "meses_historial_crediticio", "creditos_previos",
            "atrasos_previos_30d", "porcentaje_pago_puntual", "monto_solicitado_cop",
            "plazo_meses", "cuota_estimada_cop"]
TIPOS = {"ingresos_mensuales_cop": "float", "obligaciones_mensuales_cop": "float", "tipo_empleo": "str",
         "antiguedad_laboral_meses": "float", "meses_historial_crediticio": "float",
         "creditos_previos": "int", "atrasos_previos_30d": "int", "porcentaje_pago_puntual": "float",
         "monto_solicitado_cop": "float", "plazo_meses": "int", "cuota_estimada_cop": "float"}
UMBRAL = 0.5  # provisional

df = pd.read_csv(CSV)
X, y = df[FEATURES], df["incumplimiento_90d"]
X_ent, X_prueba, y_ent, y_prueba = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

pre = ColumnTransformer([
    ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("esc", StandardScaler())]), NUM),
    ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")),
                      ("oh", OneHotEncoder(handle_unknown="ignore"))]), CAT),
])
pipe = Pipeline([("pre", pre), ("clf", LogisticRegression(max_iter=1000, class_weight="balanced"))])
pipe.fit(X_ent, y_ent)
p = pipe.predict_proba(X_prueba)[:, 1]

SALIDA.mkdir(parents=True, exist_ok=True)
ruta = SALIDA / "pipeline.joblib"
joblib.dump(pipe, ruta)
sha = lambda b: hashlib.sha256(b).hexdigest()
manifiesto = {
    "model_version": VERSION, "run_id": None,
    "dataset_version": "prestamos_entrenamiento.csv", "dataset_sha256": sha(CSV.read_bytes()),
    "features": [{"nombre": f, "tipo": TIPOS[f]} for f in FEATURES],
    "clase_positiva": 1, "umbral": UMBRAL,
    "metricas": {"prueba_roc_auc": round(roc_auc_score(y_prueba, p), 4),
                 "prueba_pr_auc": round(average_precision_score(y_prueba, p), 4)},
    "dependencias": {"scikit-learn": sklearn.__version__, "pandas": pd.__version__,
                     "numpy": np.__version__, "joblib": joblib.__version__},
    "artefacto_sha256": sha(ruta.read_bytes()),
    "nota": "Modelo base provisional, sin MLflow. Reemplazar por la versión real (etapas A-F).",
}
(SALIDA / "manifest.json").write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False), encoding="utf-8")
ej = X_prueba.iloc[[0]]
ej_dict = json.loads(ej.to_json(orient="records"))[0]
(SALIDA / "ejemplo_entrada.json").write_text(json.dumps(ej_dict, indent=2, ensure_ascii=False), encoding="utf-8")
(SALIDA / "ejemplo_salida.json").write_text(json.dumps({"probabilidad_incumplimiento": round(float(pipe.predict_proba(ej)[0, 1]), 4)}, indent=2), encoding="utf-8")
(RAIZ / "ml/registry/active.json").write_text(json.dumps({
    "model_version": VERSION, "promovido_en": datetime.now(timezone.utc).isoformat(),
    "promovido_por": "base", "version_anterior": None, "motivo": "Modelo base provisional"}, indent=2), encoding="utf-8")
print(manifiesto["metricas"], "umbral", UMBRAL)
