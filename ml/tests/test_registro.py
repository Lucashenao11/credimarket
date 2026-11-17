"""Pruebas del registro: cada versión exportada cumple el contrato 4.3 y active.json apunta a una válida."""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from comun import FEATURES  # noqa: E402
from promover import ACTIVO, REGISTRO, verificar  # noqa: E402

VERSIONES = sorted(p.name for p in REGISTRO.iterdir() if p.is_dir() and p.name.startswith("v")
                   and p.name != "v0-basico")


def test_active_apunta_a_version_valida():
    assert verificar(json.loads(ACTIVO.read_text(encoding="utf-8"))["model_version"]) == []


@pytest.mark.parametrize("version", VERSIONES)
def test_version_cumple_contrato(version):
    assert verificar(version) == []


@pytest.mark.parametrize("version", VERSIONES)
def test_ejemplo_reproducible_y_none_igual_a_nan(version):
    carpeta = REGISTRO / version
    pipe = joblib.load(carpeta / "pipeline.joblib")
    entrada = json.loads((carpeta / "ejemplo_entrada.json").read_text(encoding="utf-8"))
    salida = json.loads((carpeta / "ejemplo_salida.json").read_text(encoding="utf-8"))
    assert pipe.predict_proba(pd.DataFrame([entrada])[FEATURES])[0, 1] == salida["probabilidad_incumplimiento"]
    for col in ["tipo_empleo", "porcentaje_pago_puntual", "meses_historial_crediticio"]:
        p_none = pipe.predict_proba(pd.DataFrame([dict(entrada, **{col: None})])[FEATURES])[0, 1]
        p_nan = pipe.predict_proba(pd.DataFrame([dict(entrada, **{col: np.nan})])[FEATURES])[0, 1]
        assert p_none == p_nan, col
