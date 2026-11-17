"""Prueba 11: promoción y rollback del modelo, de punta a punta contra Préstamos.

Ejecutar desde la raíz del repo, con el compose arriba y v1 activa:
    ml/.venv/bin/python ml/scripts/prueba11.py [--candidata v2]

Pasos (cada uno se verifica contra la API, no solo contra el archivo):
  1. Estado inicial: Préstamos sirve la versión de active.json.
  2. promover.py promover <candidata>  ->  docker compose restart prestamos  ->  /modelo/info dice <candidata>
     y /riesgo/predict reproduce su ejemplo_salida.json.
  3. promover.py rollback             ->  docker compose restart prestamos  ->  vuelve la versión inicial.
La salida completa queda en ml/evidencia/prueba11.log.
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from comun import DIR_ML, RAIZ  # noqa: E402
from prueba10 import CLIENTES, PRESTAMOS, get, leer_env, post  # noqa: E402

LOG = DIR_ML / "evidencia/prueba11.log"
lineas: list[str] = []


def log(msg: str) -> None:
    print(msg)
    lineas.append(msg)


def ejecutar(*cmd: str) -> None:
    log(f"$ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True)
    for linea in (r.stdout + r.stderr).strip().splitlines():
        log(f"  {linea}")
    if r.returncode:
        raise SystemExit(f"Falló: {' '.join(cmd)}")


def reiniciar_prestamos() -> None:
    ejecutar("docker", "compose", "restart", "prestamos")
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{PRESTAMOS}/health", timeout=2)
            return
        except OSError:
            time.sleep(1)
    raise SystemExit("Préstamos no respondió /health en 60 s")


def verificar(version: str, token: str) -> bool:
    info = get(f"{PRESTAMOS}/modelo/info", token)
    carpeta = DIR_ML / "registry" / version
    entrada = json.loads((carpeta / "ejemplo_entrada.json").read_text(encoding="utf-8"))
    esperado = json.loads((carpeta / "ejemplo_salida.json").read_text(encoding="utf-8"))
    r = post(f"{PRESTAMOS}/riesgo/predict", entrada, token)
    ok = (info["model_version"] == version and r["model_version"] == version
          and r["probabilidad_incumplimiento"] == esperado["probabilidad_incumplimiento"]
          and r["umbral"] == esperado["umbral"])
    log(f"  /modelo/info -> {info['model_version']} (run {info['run_id']}, umbral {info['umbral']}, "
        f"promovido_en {info['promovido_en']})")
    log(f"  /riesgo/predict(ejemplo de {version}) -> p={r['probabilidad_incumplimiento']:.6f} "
        f"{r['decision']} | esperado {esperado['probabilidad_incumplimiento']:.6f}  {'OK' if ok else 'FALLA'}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidata", default="v2")
    ap.add_argument("--por", default="Juan David")
    args = ap.parse_args()
    py = sys.executable
    log(f"Prueba 11 — {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    token = post(f"{CLIENTES}/auth/login", {"usuario": "admin",
                                            "password": leer_env()["DEMO_ADMIN_PASSWORD"]})["access_token"]
    inicial = json.loads((DIR_ML / "registry/active.json").read_text(encoding="utf-8"))["model_version"]
    if inicial == args.candidata:
        log(f"{args.candidata} ya está activa; parte de otra versión.")
        return 1

    log(f"\n1. Estado inicial (active.json = {inicial})")
    resultados = [verificar(inicial, token)]

    log(f"\n2. Promover {args.candidata}")
    ejecutar(py, "ml/scripts/promover.py", "promover", args.candidata, "--por", args.por,
             "--motivo", "Prueba 11: promover el retador")
    reiniciar_prestamos()
    resultados.append(verificar(args.candidata, token))

    log(f"\n3. Rollback")
    ejecutar(py, "ml/scripts/promover.py", "rollback", "--por", args.por,
             "--motivo", f"Prueba 11: rollback; {args.candidata} no supera a {inicial} en validación")
    reiniciar_prestamos()
    resultados.append(verificar(inicial, token))

    ok = all(resultados)
    log(f"\nPRUEBA 11 {'SUPERADA' if ok else 'FALLIDA'}: {inicial} -> {args.candidata} -> {inicial}")
    LOG.parent.mkdir(exist_ok=True)
    LOG.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
