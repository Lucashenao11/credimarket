import json
import os
from pathlib import Path

import pytest

from app.config import settings
from app.riesgo import ModeloRiesgo, calcular_cuota, construir_features
from tests.conftest import CLIENTE_OK


def test_cuota_coincide_con_el_csv():
    # Dato real del CSV: 7 464 000 a 6 meses con i = 0.018
    assert round(calcular_cuota(7_464_000, 6), 2) == 1323536.90


def test_construir_features_tiene_las_11_columnas_y_nan_en_faltantes():
    f = construir_features({**CLIENTE_OK, "porcentaje_pago_puntual": None, "tipo_empleo": None}, 3_000_000, 12)
    assert len(f) == 11 and f["porcentaje_pago_puntual"] != f["porcentaje_pago_puntual"]  # NaN
    assert f["monto_solicitado_cop"] == 3_000_000.0


@pytest.mark.skipif(not (Path(settings.model_registry_dir) / "active.json").exists(),
                    reason="no hay modelo promovido en MODEL_REGISTRY_DIR")
def test_carga_el_modelo_promovido_y_predice():
    m = ModeloRiesgo(settings.model_registry_dir)
    assert m.version == json.loads((Path(settings.model_registry_dir) / "active.json").read_text())["model_version"]
    for cliente in (CLIENTE_OK, {**CLIENTE_OK, "tipo_empleo": None, "porcentaje_pago_puntual": None,
                                 "antiguedad_laboral_meses": None, "meses_historial_crediticio": None}):
        p = m.predecir(construir_features(cliente, 3_000_000, 12))
        assert 0.0 <= p <= 1.0
