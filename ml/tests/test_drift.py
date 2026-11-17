"""Pruebas del PSI: agrupación correcta, PSI 0 sin cambio y PSI alto con un cambio claro."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import etapa_f_drift as F  # noqa: E402

rng = np.random.default_rng(0)
REF = pd.Series(np.r_[rng.lognormal(15, 0.5, 5000), [np.nan] * 100])


def test_deciles_reparten_la_referencia():
    p = F.proporciones(REF, F.grupos_referencia(REF, False), False)
    assert abs(p.sum() - 1) < 1e-9
    assert p.drop(F.FALTANTE).between(0.09, 0.11).all()  # el bug de etiquetas dejaba grupos en 0


def test_psi_cero_con_la_misma_distribucion():
    assert F.psi_columna(REF, REF, False)[0] < 1e-12


def test_psi_detecta_un_desplazamiento():
    assert F.psi_columna(REF, REF * 1.5, False)[0] > F.MODERADO


def test_psi_detecta_aumento_de_faltantes():
    actual = REF.copy()
    actual.iloc[:1500] = np.nan
    assert F.psi_columna(REF, actual, False)[0] > F.ESTABLE


def test_categoricas_y_valores_nuevos():
    ref = pd.Series(["a"] * 50 + ["b"] * 50)
    assert F.psi_columna(ref, pd.Series(["a"] * 50 + ["c"] * 50), True)[0] > F.MODERADO
