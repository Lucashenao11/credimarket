"""Etapa A: validación, análisis exploratorio, hash SHA-256 y particiones 60/20/20.

Ejecutar desde la raíz del repo:  ml/.venv/bin/python ml/scripts/etapa_a_datos.py

Salidas (se versionan en Git, son evidencia y entrada de las etapas siguientes):
  ml/data/particiones.csv        solicitud_id -> entrenamiento | validacion | prueba
  ml/data/particiones_meta.json  semilla, hashes del CSV y de las particiones, tamaños
  ml/reporte_datos.md            validación y análisis exploratorio

Si una validación "dura" falla, el script termina con código 1 y NO escribe particiones:
no se entrena con datos que rompen el contrato.
"""
import json
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from comun import (CATEGORIA_FALTANTE, CATEGORIAS_EMPLEO, CSV_ENTRENAMIENTO, CSV_NUEVAS, CSV_PARTICIONES, DIR_ML,
                   EXCLUIDAS, FEATURES, ID, NUM, OBJETIVO, PLAZOS, SEMILLA, TASA_MENSUAL, cuota,
                   sha256_archivo)

# Faltantes permitidos según el contrato 4.3
PERMITE_FALTANTE = {"tipo_empleo", "antiguedad_laboral_meses", "meses_historial_crediticio",
                    "porcentaje_pago_puntual"}
ENTEROS = ["creditos_previos", "atrasos_previos_30d", "plazo_meses"]
# Rangos plausibles (mín, máx) por dominio: dinero > 0, conteos >= 0, porcentaje en [0, 100]
RANGOS = {
    "ingresos_mensuales_cop": (1, None), "obligaciones_mensuales_cop": (0, None),
    "antiguedad_laboral_meses": (0, 600), "meses_historial_crediticio": (0, 600),
    "creditos_previos": (0, None), "atrasos_previos_30d": (0, None),
    "porcentaje_pago_puntual": (0, 100), "monto_solicitado_cop": (1, None),
    "cuota_estimada_cop": (1, None),
}
COLUMNAS_ESPERADAS = ["solicitud_id", "cliente_id", *FEATURES[:10], "tasa_mensual_simulada",
                      "cuota_estimada_cop"]


def tabla_md(df: pd.DataFrame, indice: bool = True) -> str:
    d = df.reset_index() if indice else df
    filas = ["| " + " | ".join(map(str, d.columns)) + " |", "|" + "---|" * len(d.columns)]
    filas += ["| " + " | ".join(map(str, r)) + " |" for r in d.itertuples(index=False)]
    return "\n".join(filas)


def validar(df: pd.DataFrame, con_etiqueta: bool) -> tuple[list[str], list[str], dict]:
    """Devuelve (errores, avisos, hechos). Errores = rompen el contrato; avisos = a documentar."""
    errores, avisos, h = [], [], {}
    esperadas = COLUMNAS_ESPERADAS + ([OBJETIVO] if con_etiqueta else [])
    faltan = set(esperadas) - set(df.columns)
    sobran = set(df.columns) - set(esperadas)
    if faltan:
        errores.append(f"Faltan columnas: {sorted(faltan)}")
        return errores, avisos, h
    if sobran:
        avisos.append(f"Columnas no esperadas (se ignoran): {sorted(sobran)}")

    # Tipos
    for c in NUM:
        if not pd.api.types.is_numeric_dtype(df[c]):
            errores.append(f"{c} no es numérica (dtype {df[c].dtype})")
    for c in ENTEROS:
        v = df[c].dropna()
        if (v != np.round(v)).any():
            errores.append(f"{c} tiene valores no enteros")

    # Duplicados
    h["filas"] = len(df)
    h["ids_duplicados"] = int(df[ID].duplicated().sum())
    h["clientes_repetidos"] = int(df["cliente_id"].duplicated().sum())
    h["filas_duplicadas"] = int(df.duplicated().sum())
    cols_sin_id = [c for c in df.columns if c not in (ID, "cliente_id")]
    h["duplicados_sin_ids"] = int(df.duplicated(subset=cols_sin_id).sum())
    h["duplicados_features_etiqueta_distinta"] = 0
    if con_etiqueta:
        grupos = df.groupby(FEATURES, dropna=False)[OBJETIVO].nunique()
        h["duplicados_features_etiqueta_distinta"] = int((grupos > 1).sum())
    if h["ids_duplicados"]:
        errores.append(f"{h['ids_duplicados']} solicitud_id duplicados")
    if h["clientes_repetidos"]:
        avisos.append(f"{h['clientes_repetidos']} clientes con más de una solicitud: "
                      "habría que partir por cliente para evitar fuga")
    if h["duplicados_sin_ids"]:
        avisos.append(f"{h['duplicados_sin_ids']} filas idénticas salvo los identificadores")

    # Faltantes
    h["faltantes"] = {c: int(n) for c, n in df[FEATURES].isna().sum().items()}
    for c, n in h["faltantes"].items():
        if n and c not in PERMITE_FALTANTE:
            errores.append(f"{c} tiene {n} faltantes y el contrato no los permite")
    if con_etiqueta and df[OBJETIVO].isna().any():
        errores.append("La etiqueta tiene faltantes")

    # Rangos y dominios
    h["fuera_de_rango"] = {}
    for c, (lo, hi) in RANGOS.items():
        v = df[c].dropna()
        n = int((v < (lo if lo is not None else -np.inf)).sum() + (v > (hi if hi is not None else np.inf)).sum())
        h["fuera_de_rango"][c] = n
        if n:
            errores.append(f"{c}: {n} valores fuera de [{lo}, {hi}]")
    otras = set(df["tipo_empleo"].dropna().unique()) - set(CATEGORIAS_EMPLEO)
    if otras:
        errores.append(f"tipo_empleo con categorías desconocidas: {sorted(otras)}")
    plazos = set(df["plazo_meses"].unique()) - set(PLAZOS)
    if plazos:
        avisos.append(f"plazo_meses con valores fuera de {PLAZOS}: {sorted(plazos)}")
    if not np.allclose(df["tasa_mensual_simulada"], TASA_MENSUAL):
        errores.append("tasa_mensual_simulada no es constante 0.018: revisar la exclusión")
    if con_etiqueta and not set(df[OBJETIVO].unique()) <= {0, 1}:
        errores.append("La etiqueta tiene valores distintos de 0 y 1")

    # Consistencia de la cuota con la fórmula del contrato
    esperada = cuota(df["monto_solicitado_cop"], df["plazo_meses"])
    err_rel = ((df["cuota_estimada_cop"] - esperada).abs() / esperada)
    h["cuota_error_relativo_max"] = float(err_rel.max())
    if (err_rel > 1e-6).any():
        errores.append(f"{int((err_rel > 1e-6).sum())} cuotas no coinciden con la fórmula")

    # Estructura de faltantes: ¿falta el % de pago puntual justo cuando no hay créditos previos?
    sin_hist = df["creditos_previos"] == 0
    falta_pp = df["porcentaje_pago_puntual"].isna()
    h["pago_puntual_falta_y_sin_creditos"] = int((falta_pp & sin_hist).sum())
    h["pago_puntual_falta_con_creditos"] = int((falta_pp & ~sin_hist).sum())
    h["sin_creditos_con_pago_puntual"] = int((~falta_pp & sin_hist).sum())
    h["obligaciones_mayores_que_ingresos"] = int(
        (df["obligaciones_mensuales_cop"] > df["ingresos_mensuales_cop"]).sum())
    if h["obligaciones_mayores_que_ingresos"]:
        avisos.append(f"{h['obligaciones_mayores_que_ingresos']} solicitudes con obligaciones > ingresos "
                      "(posible pero extremo; se conservan)")
    return errores, avisos, h


def particionar(df: pd.DataFrame) -> pd.DataFrame:
    """60/20/20 estratificado por la etiqueta. Dos cortes: 60 | 40, y el 40 se parte en 20 | 20."""
    ent, resto = train_test_split(df[[ID, OBJETIVO]], test_size=0.4, stratify=df[OBJETIVO],
                                  random_state=SEMILLA)
    val, prueba = train_test_split(resto, test_size=0.5, stratify=resto[OBJETIVO],
                                   random_state=SEMILLA)
    part = pd.concat([ent.assign(particion="entrenamiento"), val.assign(particion="validacion"),
                      prueba.assign(particion="prueba")])
    return part[[ID, "particion"]].sort_values(ID).reset_index(drop=True)


def tasa_por(df: pd.DataFrame, clave) -> pd.DataFrame:
    t = df.groupby(clave, dropna=False, observed=True)[OBJETIVO].agg(["size", "mean"])
    t.columns = ["n", "tasa_incumplimiento"]
    t["tasa_incumplimiento"] = (t["tasa_incumplimiento"] * 100).round(1).astype(str) + " %"
    return t


def eda(df: pd.DataFrame) -> list[str]:
    s = []
    desc = df[NUM].describe(percentiles=[.01, .5, .99]).T
    desc["faltantes"] = df[NUM].isna().sum()
    desc["asimetria"] = df[NUM].skew()
    s += ["### Resumen de variables numéricas", "",
          tabla_md(desc[["count", "faltantes", "mean", "std", "min", "1%", "50%", "99%", "max", "asimetria"]]
                   .round(2)), ""]

    s += ["### Incumplimiento por variable categórica y por plazo", "",
          tabla_md(tasa_por(df.assign(tipo_empleo=df["tipo_empleo"].fillna("(faltante)")), "tipo_empleo")), "",
          tabla_md(tasa_por(df, "plazo_meses")), ""]

    # Variables derivadas solo para el análisis (no entran al modelo: el contrato son 11 columnas)
    d = df.assign(
        carga_obligaciones=df["obligaciones_mensuales_cop"] / df["ingresos_mensuales_cop"],
        carga_cuota=df["cuota_estimada_cop"] / df["ingresos_mensuales_cop"],
        sin_historial=df["porcentaje_pago_puntual"].isna(),
    )
    s += ["### Incumplimiento por quintil (variables clave)", ""]
    for c in ["ingresos_mensuales_cop", "atrasos_previos_30d", "porcentaje_pago_puntual",
              "carga_obligaciones", "carga_cuota"]:
        q = pd.qcut(d[c], 5, duplicates="drop")
        t = tasa_por(d.assign(**{c: q}), c)
        s += [f"**{c}**", "", tabla_md(t), ""]
    s += ["**Sin historial crediticio (porcentaje_pago_puntual faltante)**", "",
          tabla_md(tasa_por(d, "sin_historial")), ""]

    # Correlaciones de Spearman (monótonas, robustas a la asimetría de las variables en COP)
    cols = NUM + ["carga_obligaciones", "carga_cuota"]
    rho_y = d[cols + [OBJETIVO]].corr(method="spearman")[OBJETIVO].drop(OBJETIVO)
    rho_y = rho_y.reindex(rho_y.abs().sort_values(ascending=False).index).round(3).to_frame("rho_spearman")
    s += ["### Correlación de Spearman con la etiqueta", "", tabla_md(rho_y), ""]
    m = d[NUM].corr(method="spearman")
    pares = [(a, b, round(m.loc[a, b], 3)) for i, a in enumerate(NUM) for b in NUM[i + 1:]
             if abs(m.loc[a, b]) >= 0.6]
    s += ["### Pares de variables de entrada con |rho| ≥ 0,6 (redundancia)", "",
          tabla_md(pd.DataFrame(pares, columns=["variable_a", "variable_b", "rho"]), indice=False)
          if pares else "Ninguno.", ""]
    return s


def main() -> int:
    df = pd.read_csv(CSV_ENTRENAMIENTO)
    nuevas = pd.read_csv(CSV_NUEVAS)
    sha_csv = sha256_archivo(CSV_ENTRENAMIENTO)

    errores, avisos, h = validar(df, con_etiqueta=True)
    err_n, avisos_n, h_n = validar(nuevas, con_etiqueta=False)
    for e in errores:
        print("ERROR:", e)
    for e in err_n:
        print("ERROR (solicitudes_nuevas):", e)
    if errores:
        return 1  # no se particiona ni se entrena con datos inválidos

    part = particionar(df)
    part.to_csv(CSV_PARTICIONES, index=False, lineterminator="\n")
    sha_part = sha256_archivo(CSV_PARTICIONES)
    resumen = (df[[ID, OBJETIVO]].merge(part, on=ID).groupby("particion")[OBJETIVO]
               .agg(["size", "sum", "mean"]).reindex(["entrenamiento", "validacion", "prueba"]))
    resumen.columns = ["filas", "incumplimientos", "tasa"]
    resumen["tasa"] = (resumen["tasa"] * 100).round(2).astype(str) + " %"

    meta = {
        "generado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset_version": CSV_ENTRENAMIENTO.name,
        "dataset_sha256": sha_csv,
        "particiones_sha256": sha_part,
        "estrategia": "train_test_split estratificado por incumplimiento_90d: 60/40 y luego 50/50 del 40",
        "semilla": SEMILLA,
        "tamanos": {p: int(r.filas) for p, r in resumen.iterrows()},
        "features": FEATURES,
        "excluidas": EXCLUIDAS,
    }
    (CSV_PARTICIONES.parent / "particiones_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    tasa = df[OBJETIVO].mean()
    r = [
        "# Etapa A — Validación y análisis exploratorio de los datos", "",
        f"Generado por `ml/scripts/etapa_a_datos.py` el {meta['generado_en']}. No editar a mano.", "",
        "## Identificación del conjunto de datos", "",
        f"- Archivo: `ml/data/{CSV_ENTRENAMIENTO.name}`",
        f"- SHA-256: `{sha_csv}`",
        f"- Filas: {h['filas']:,}; columnas: {df.shape[1]}",
        f"- Clase positiva (1 = incumplimiento a 90 días): {int(df[OBJETIVO].sum()):,} "
        f"({tasa:.1%}). Desbalance moderado (≈ 1:{(1 - tasa) / tasa:.1f}): no se usa accuracy "
        f"(un modelo que siempre dice 0 tendría {1 - tasa:.1%}).", "",
        "## Validación", "",
        "Resultado: **sin errores**." if not errores else "", "",
        "| Comprobación | Resultado |", "|---|---|",
        f"| Columnas esperadas presentes | sí |",
        f"| `solicitud_id` duplicados | {h['ids_duplicados']} |",
        f"| Clientes con más de una solicitud | {h['clientes_repetidos']} |",
        f"| Filas duplicadas (completas / sin identificadores) | {h['filas_duplicadas']} / {h['duplicados_sin_ids']} |",
        f"| Mismas variables con etiqueta distinta | {h['duplicados_features_etiqueta_distinta']} |",
        f"| Valores fuera de rango | {sum(h['fuera_de_rango'].values())} |",
        f"| `tipo_empleo` fuera de {CATEGORIAS_EMPLEO} | 0 |",
        f"| `tasa_mensual_simulada` constante = {TASA_MENSUAL} | sí |",
        f"| Error relativo máximo de `cuota_estimada_cop` vs. la fórmula | {h['cuota_error_relativo_max']:.1e} |",
        f"| Obligaciones > ingresos | {h['obligaciones_mayores_que_ingresos']} |", "",
        "Rangos comprobados: " + "; ".join(f"`{c}` ∈ [{lo}, {hi if hi is not None else '∞'}]"
                                          for c, (lo, hi) in RANGOS.items()) + ".", "",
        *([f"Avisos: " + " ".join(avisos), ""] if avisos else []),
        "### Faltantes", "",
        "| Variable | Faltantes | % | Permitido por el contrato |", "|---|---|---|---|",
        *[f"| `{c}` | {n:,} | {n / len(df):.2%} | {'sí' if c in PERMITE_FALTANTE else 'no'} |"
          for c, n in h["faltantes"].items() if n],
        "",
        f"`porcentaje_pago_puntual` falta en {h['pago_puntual_falta_y_sin_creditos']:,} filas con "
        f"`creditos_previos = 0` y en {h['pago_puntual_falta_con_creditos']} filas con créditos; hay "
        f"{h['sin_creditos_con_pago_puntual']} filas sin créditos que sí lo tengan. Es un faltante "
        "**estructural** (no hay historial que medir), no aleatorio.", "",
        "## Decisiones de preprocesamiento (dentro del pipeline, ajustadas solo con entrenamiento)", "",
        "- **Variables excluidas:** " + "; ".join(f"`{c}` ({m})" for c, m in EXCLUIDAS.items()) + ".",
        "- **Numéricas:** imputación por mediana (robusta a la asimetría de las variables en COP) "
        "+ indicador de faltante (`add_indicator=True`), para no hacer pasar a un cliente sin historial "
        "por uno con historial mediano; luego `StandardScaler` (necesario para la regresión logística; "
        "inocuo para árboles).",
        f"- **Categórica (`tipo_empleo`):** faltante → categoría explícita `\"{CATEGORIA_FALTANTE}\"` y "
        "one-hot con `handle_unknown=\"ignore\"`. Se prefiere a la moda porque los faltantes incumplen "
        "más que la moda (ver tabla abajo; n pequeño, evidencia débil) y porque no inventa un dato. "
        "Dos imputadores en cadena (uno para `NaN`, otro para `None`) garantizan que la API y la "
        "solicitud real den la misma probabilidad (prueba 10).",
        "- **Particiones antes de cualquier ajuste:** la mediana, la media y la desviación del escalado "
        "y las categorías del one-hot se calculan con `fit` sobre entrenamiento únicamente; validación "
        "y prueba solo pasan por `transform`. Así no hay fuga de información.", "",
        "## Particiones", "",
        f"Estratificadas por la etiqueta, semilla `{SEMILLA}`. Como cada cliente tiene una sola "
        "solicitud, no hace falta partir por grupos. Identificadores en `ml/data/particiones.csv` "
        f"(SHA-256 `{sha_part}`).", "",
        tabla_md(resumen), "",
        "Uso: **entrenamiento** para ajustar; **validación** para comparar candidatos y elegir el "
        "umbral; **prueba** una sola vez, con el modelo y el umbral ya congelados.", "",
        "## Análisis exploratorio", "",
        *eda(df),
        "## Solicitudes nuevas (para la etapa F)", "",
        f"`ml/data/{CSV_NUEVAS.name}`: {h_n['filas']:,} filas, SHA-256 `{sha256_archivo(CSV_NUEVAS)}`, "
        f"{'sin errores de validación' if not err_n else 'errores: ' + '; '.join(err_n)}. "
        "Faltantes: " + ", ".join(f"`{c}` {n}" for c, n in h_n["faltantes"].items() if n) + ".", "",
    ]
    (DIR_ML / "reporte_datos.md").write_text("\n".join(r), encoding="utf-8")
    print(f"OK  sha256={sha_csv}")
    print(resumen.to_string())
    for a in avisos:
        print("AVISO:", a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
