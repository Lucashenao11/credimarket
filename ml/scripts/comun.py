"""Constantes y piezas compartidas por las etapas A a F del ML.

Contrato 4.3 (docs/plan-equipo.md): las 11 columnas de FEATURES, en ese orden, son la
entrada del pipeline exportado. Préstamos construye exactamente estas columnas.

Regla importante: el pipeline que se exporta solo puede usar clases de scikit-learn.
Si usara una función o clase definida aquí, Préstamos tendría que importar este módulo
para deserializar el joblib, y no lo tiene.
"""
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

RAIZ = Path(__file__).resolve().parents[2]
DIR_ML = RAIZ / "ml"
CSV_ENTRENAMIENTO = DIR_ML / "data/prestamos_entrenamiento.csv"
CSV_NUEVAS = DIR_ML / "data/solicitudes_nuevas.csv"
CSV_PARTICIONES = DIR_ML / "data/particiones.csv"

SEMILLA = 42
OBJETIVO = "incumplimiento_90d"  # clase_positiva = 1: incumple a 90 días
ID = "solicitud_id"

FEATURES = ["ingresos_mensuales_cop", "obligaciones_mensuales_cop", "tipo_empleo",
            "antiguedad_laboral_meses", "meses_historial_crediticio", "creditos_previos",
            "atrasos_previos_30d", "porcentaje_pago_puntual", "monto_solicitado_cop",
            "plazo_meses", "cuota_estimada_cop"]
TIPOS = {"ingresos_mensuales_cop": "float", "obligaciones_mensuales_cop": "float", "tipo_empleo": "str",
         "antiguedad_laboral_meses": "float", "meses_historial_crediticio": "float",
         "creditos_previos": "int", "atrasos_previos_30d": "int", "porcentaje_pago_puntual": "float",
         "monto_solicitado_cop": "float", "plazo_meses": "int", "cuota_estimada_cop": "float"}
CAT = ["tipo_empleo"]
NUM = [f for f in FEATURES if f not in CAT]
CATEGORIAS_EMPLEO = ["dependiente", "independiente", "temporal"]
EXCLUIDAS = {"solicitud_id": "identificador", "cliente_id": "identificador",
             "tasa_mensual_simulada": "constante (0.018): varianza cero, no aporta información",
             OBJETIVO: "etiqueta"}
TASA_MENSUAL = 0.018
PLAZOS = [6, 12, 18, 24, 36]
CATEGORIA_FALTANTE = "desconocido"


def sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def cuota(monto, plazo, i=TASA_MENSUAL):
    """Cuota fija (sistema francés), la misma fórmula que usa Préstamos."""
    return monto * i / (1 - (1 + i) ** (-plazo))


def cargar_entrenamiento() -> pd.DataFrame:
    return pd.read_csv(CSV_ENTRENAMIENTO)


def cargar_particiones() -> dict[str, pd.DataFrame]:
    """Devuelve {'entrenamiento': df, 'validacion': df, 'prueba': df} según particiones.csv."""
    df = cargar_entrenamiento()
    part = pd.read_csv(CSV_PARTICIONES)
    df = df.merge(part, on=ID, how="inner", validate="one_to_one")
    return {p: g.drop(columns="particion").reset_index(drop=True) for p, g in df.groupby("particion")}


def construir_preprocesador(escalar: bool = True) -> ColumnTransformer:
    """Imputación, codificación y escalado. Se ajusta SOLO con entrenamiento (dentro del Pipeline).

    Numéricas: mediana + indicador de faltante. El indicador importa sobre todo en
    porcentaje_pago_puntual, que falta exactamente cuando creditos_previos == 0 (sin historial):
    la mediana sola haría parecer que el cliente tiene un historial típico.

    Categórica (tipo_empleo): dos imputadores en cadena porque SimpleImputer reconoce un solo
    marcador de faltante. El primero cubre NaN y el segundo None; ambos llevan a la categoría
    explícita "desconocido". Así la API (que puede pasar None) y la solicitud real (NaN) dan la
    misma probabilidad. handle_unknown="ignore": una categoría nunca vista no rompe la predicción.
    """
    pasos_num = [("imputar", SimpleImputer(strategy="median", add_indicator=True))]
    if escalar:
        pasos_num.append(("escalar", StandardScaler()))
    categorica = Pipeline([
        ("imputar_nan", SimpleImputer(missing_values=np.nan, strategy="constant",
                                      fill_value=CATEGORIA_FALTANTE)),
        ("imputar_none", SimpleImputer(missing_values=None, strategy="constant",
                                       fill_value=CATEGORIA_FALTANTE)),
        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    return ColumnTransformer([
        ("num", Pipeline(pasos_num), NUM),
        ("cat", categorica, CAT),
    ], remainder="drop", verbose_feature_names_out=True)
