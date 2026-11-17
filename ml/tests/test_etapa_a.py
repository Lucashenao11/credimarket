"""Pruebas de la etapa A: particiones y equivalencia None/NaN del preprocesador."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from comun import (CSV_PARTICIONES, FEATURES, ID, OBJETIVO, cargar_entrenamiento,  # noqa: E402
                   cargar_particiones, construir_preprocesador)


@pytest.fixture(scope="module")
def particiones():
    return cargar_particiones()


def test_particiones_disjuntas_y_completas(particiones):
    ids = {p: set(d[ID]) for p, d in particiones.items()}
    assert set(ids) == {"entrenamiento", "validacion", "prueba"}
    assert not (ids["entrenamiento"] & ids["validacion"])
    assert not (ids["entrenamiento"] & ids["prueba"])
    assert not (ids["validacion"] & ids["prueba"])
    assert set().union(*ids.values()) == set(cargar_entrenamiento()[ID])


def test_particiones_60_20_20_estratificadas(particiones):
    n = sum(len(d) for d in particiones.values())
    tasa = cargar_entrenamiento()[OBJETIVO].mean()
    for p, frac in [("entrenamiento", .6), ("validacion", .2), ("prueba", .2)]:
        assert len(particiones[p]) == pytest.approx(n * frac, abs=1)
        assert particiones[p][OBJETIVO].mean() == pytest.approx(tasa, abs=0.005)


def test_preprocesador_trata_none_y_nan_igual(particiones):
    pre = construir_preprocesador().fit(particiones["entrenamiento"][FEATURES])
    fila = particiones["validacion"][FEATURES].iloc[[0]].to_dict("records")[0]
    for col in ["tipo_empleo", "porcentaje_pago_puntual", "antiguedad_laboral_meses"]:
        con_none = pre.transform(pd.DataFrame([dict(fila, **{col: None})], columns=FEATURES))
        con_nan = pre.transform(pd.DataFrame([dict(fila, **{col: np.nan})], columns=FEATURES))
        np.testing.assert_array_equal(con_none, con_nan, err_msg=col)


def test_tipo_empleo_faltante_va_a_desconocido(particiones):
    pre = construir_preprocesador().fit(particiones["entrenamiento"][FEATURES])
    nombres = list(pre.get_feature_names_out())
    fila = particiones["validacion"][FEATURES].iloc[[0]].to_dict("records")[0]
    x = pre.transform(pd.DataFrame([dict(fila, tipo_empleo=None)], columns=FEATURES))[0]
    assert x[nombres.index("cat__tipo_empleo_desconocido")] == 1


def test_archivo_particiones_versionado():
    assert CSV_PARTICIONES.exists(), "Ejecuta ml/scripts/etapa_a_datos.py"
