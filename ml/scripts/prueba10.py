"""Prueba 10: la probabilidad del pipeline exportado y la de POST /riesgo/predict deben ser iguales.

Ejecutar desde la raíz del repo, con el compose arriba y Préstamos reiniciado tras la promoción:
    ml/.venv/bin/python ml/scripts/prueba10.py

Compara, para la versión ACTIVA (active.json):
  - el ejemplo oficial (ejemplo_entrada.json vs. ejemplo_salida.json vs. API), y
  - 10 solicitudes completas y hasta 3 por cada columna con faltantes (se envían como null).
Tolerancia: 1e-12 (mismo pipeline, mismas versiones: deberían coincidir bit a bit).
La contraseña del admin de demo se lee de .env (nunca se imprime).
"""
import json
import math
import sys
import urllib.request
from pathlib import Path

import joblib
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from comun import DIR_ML, FEATURES, ID, RAIZ, cargar_particiones  # noqa: E402

PRESTAMOS = "http://localhost:8003"
CLIENTES = "http://localhost:8002"
TOLERANCIA = 1e-12


def leer_env() -> dict:
    env = {}
    for linea in (RAIZ / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in linea and not linea.lstrip().startswith("#"):
            k, v = linea.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def post(url: str, cuerpo: dict, token: str | None = None) -> dict:
    cab = {"Content-Type": "application/json"}
    if token:
        cab["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode(), headers=cab, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def a_json(fila: dict) -> dict:
    return {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in fila.items()}


def main() -> int:
    activo = json.loads((DIR_ML / "registry/active.json").read_text(encoding="utf-8"))
    version = activo["model_version"]
    carpeta = DIR_ML / "registry" / version
    pipe = joblib.load(carpeta / "pipeline.joblib")
    token = post(f"{CLIENTES}/auth/login", {"usuario": "admin",
                                            "password": leer_env()["DEMO_ADMIN_PASSWORD"]})["access_token"]
    info = get(f"{PRESTAMOS}/modelo/info", token)
    if info["model_version"] != version:
        print(f"Préstamos sirve {info['model_version']} pero active.json dice {version}: "
              "ejecuta  docker compose restart prestamos")
        return 1

    prueba = cargar_particiones()["prueba"].sort_values(ID)
    # Hasta 3 filas por cada columna con faltantes: incluye tipo_empleo, el caso del fallo None vs NaN
    con_faltantes = pd.concat([prueba[prueba[c].isna()].head(3) for c in FEATURES
                               if prueba[c].isna().any()]).drop_duplicates(ID)
    completas = prueba[~prueba[FEATURES].isna().any(axis=1)].head(10)
    casos = [("ejemplo_entrada.json", json.loads((carpeta / "ejemplo_entrada.json").read_text(encoding="utf-8")))]
    casos += [(r[ID], a_json(r[FEATURES].to_dict())) for _, r in pd.concat([completas, con_faltantes]).iterrows()]

    fallos = 0
    print(f"Versión activa: {version}  (umbral {info['umbral']})")
    print(f"{'caso':22s} {'faltantes':28s} {'pipeline':>12s} {'API':>12s} {'|dif|':>9s}")
    for nombre, entrada in casos:
        p_pipe = float(pipe.predict_proba(pd.DataFrame([entrada])[FEATURES])[0, 1])
        r = post(f"{PRESTAMOS}/riesgo/predict", entrada, token)
        dif = abs(p_pipe - r["probabilidad_incumplimiento"])
        ok = dif <= TOLERANCIA and r["model_version"] == version
        fallos += not ok
        nulos = ",".join(k.split("_")[0] for k, v in entrada.items() if v is None) or "-"
        print(f"{nombre:22s} {nulos:28s} {p_pipe:12.8f} {r['probabilidad_incumplimiento']:12.8f} "
              f"{dif:9.1e} {'OK' if ok else 'FALLA'}")
    esperado = json.loads((carpeta / "ejemplo_salida.json").read_text(encoding="utf-8"))
    p_ej = post(f"{PRESTAMOS}/riesgo/predict", casos[0][1], token)["probabilidad_incumplimiento"]
    if abs(p_ej - esperado["probabilidad_incumplimiento"]) > TOLERANCIA:
        print("FALLA: la API no reproduce ejemplo_salida.json")
        fallos += 1
    print(f"\n{len(casos) - fallos if fallos <= len(casos) else 0}/{len(casos)} casos iguales. "
          + ("PRUEBA 10 SUPERADA" if not fallos else f"{fallos} FALLOS"))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
