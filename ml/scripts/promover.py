"""Promoción y rollback del modelo. ÚNICO archivo que modifica: ml/registry/active.json (decisión D7).

Uso (desde la raíz del repo; solo usa la biblioteca estándar):
    python ml/scripts/promover.py promover v1 --motivo "Primera versión con selección y umbral" --por "Juan David"
    python ml/scripts/promover.py rollback --motivo "v2 rechaza demasiado" --por "Juan David"
    python ml/scripts/promover.py estado

Después: docker compose restart prestamos  (Préstamos lee active.json solo al iniciar).

Antes de promover verifica lo mismo que Préstamos al arrancar, para no dejarlo caído:
la carpeta y los archivos existen, el SHA-256 de pipeline.joblib coincide con el manifiesto,
las 11 columnas están en el orden del contrato, clase_positiva = 1 y el umbral está en (0, 1).
"""
import argparse
import getpass
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REGISTRO = Path(__file__).resolve().parents[1] / "registry"
ACTIVO = REGISTRO / "active.json"
CONTRATO = ["ingresos_mensuales_cop", "obligaciones_mensuales_cop", "tipo_empleo",
            "antiguedad_laboral_meses", "meses_historial_crediticio", "creditos_previos",
            "atrasos_previos_30d", "porcentaje_pago_puntual", "monto_solicitado_cop",
            "plazo_meses", "cuota_estimada_cop"]
ARCHIVOS = ["pipeline.joblib", "manifest.json", "ejemplo_entrada.json", "ejemplo_salida.json"]


def verificar(version: str) -> list[str]:
    carpeta = REGISTRO / version
    errores = [f"falta {carpeta / a}" for a in ARCHIVOS if not (carpeta / a).is_file()]
    if errores:
        return errores
    m = json.loads((carpeta / "manifest.json").read_text(encoding="utf-8"))
    if m.get("model_version") != version:
        errores.append(f"manifest.model_version = {m.get('model_version')!r}, se esperaba {version!r}")
    sha = hashlib.sha256((carpeta / "pipeline.joblib").read_bytes()).hexdigest()
    if sha != m.get("artefacto_sha256"):
        errores.append("el SHA-256 de pipeline.joblib no coincide con artefacto_sha256")
    if [f.get("nombre") for f in m.get("features", [])] != CONTRATO:
        errores.append("las features no son las 11 del contrato 4.3, en ese orden")
    if m.get("clase_positiva") != 1:
        errores.append("clase_positiva debe ser 1")
    if not (isinstance(m.get("umbral"), (int, float)) and 0 < m["umbral"] < 1):
        errores.append("umbral ausente o fuera de (0, 1)")
    return errores


def leer_activo() -> dict:
    return json.loads(ACTIVO.read_text(encoding="utf-8")) if ACTIVO.exists() else {}


def escribir_activo(datos: dict) -> None:
    """Escritura atómica: si el proceso muere a la mitad, active.json queda con la versión anterior."""
    tmp = ACTIVO.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, ACTIVO)


def cambiar(version: str, motivo: str, por: str, accion: str) -> int:
    errores = verificar(version)
    if errores:
        print(f"No se {accion} {version}:")
        for e in errores:
            print("  -", e)
        return 1
    actual = leer_activo()
    if actual.get("model_version") == version:
        print(f"{version} ya es la versión activa; no se cambia nada.")
        return 1
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    historial = actual.get("historial", [])
    historial.append({"accion": accion, "model_version": version, "desde": actual.get("model_version"),
                      "en": ahora, "por": por, "motivo": motivo})
    escribir_activo({"model_version": version, "promovido_en": ahora, "promovido_por": por,
                     "version_anterior": actual.get("model_version"), "motivo": motivo,
                     "historial": historial})
    print(f"{accion}: {actual.get('model_version')} -> {version}. "
          "Aplica con: docker compose restart prestamos")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("promover")
    p.add_argument("version")
    r = sub.add_parser("rollback", help="vuelve a version_anterior")
    for s in (p, r):
        s.add_argument("--motivo", required=True)
        s.add_argument("--por", default=getpass.getuser())
    sub.add_parser("estado")
    args = ap.parse_args()

    if args.comando == "estado":
        a = leer_activo()
        print(json.dumps(a, indent=2, ensure_ascii=False))
        return 0
    if args.comando == "promover":
        return cambiar(args.version, args.motivo, args.por, "promovido")
    anterior = leer_activo().get("version_anterior")
    if not anterior:
        print("No hay version_anterior en active.json: no hay a dónde hacer rollback.")
        return 1
    return cambiar(anterior, args.motivo, args.por, "rollback")


if __name__ == "__main__":
    sys.exit(main())
