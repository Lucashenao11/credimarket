"""Carga del modelo promovido (active.json) y cálculo de las mismas características del entrenamiento."""
import hashlib
import json
import math
from pathlib import Path


def calcular_cuota(monto: float, plazo_meses: int, tasa: float = 0.018) -> float:
    """cuota = monto * i / (1 - (1 + i) ** -n)"""
    return monto * tasa / (1 - (1 + tasa) ** -plazo_meses)


def construir_features(cliente: dict, monto: int, plazo_meses: int, tasa: float = 0.018) -> dict:
    nan = float("nan")

    def v(clave):
        valor = cliente.get(clave)
        return nan if valor is None else valor

    return {
        "ingresos_mensuales_cop": cliente["ingresos_mensuales_cop"],
        "obligaciones_mensuales_cop": cliente["obligaciones_mensuales_cop"],
        "tipo_empleo": v("tipo_empleo"),
        "antiguedad_laboral_meses": v("antiguedad_laboral_meses"),
        "meses_historial_crediticio": v("meses_historial_crediticio"),
        "creditos_previos": cliente["creditos_previos"],
        "atrasos_previos_30d": cliente["atrasos_previos_30d"],
        "porcentaje_pago_puntual": v("porcentaje_pago_puntual"),
        "monto_solicitado_cop": float(monto),
        "plazo_meses": plazo_meses,
        "cuota_estimada_cop": calcular_cuota(monto, plazo_meses, tasa),
    }


class ModeloRiesgo:
    """El pipeline se carga UNA vez al iniciar, desde la versión que dice active.json."""

    def __init__(self, directorio: str):
        import joblib  # importación diferida: las pruebas con un modelo falso no la necesitan

        raiz = Path(directorio)
        self.activo = json.loads((raiz / "active.json").read_text(encoding="utf-8"))
        self.version = self.activo["model_version"]
        carpeta = raiz / self.version
        self.manifiesto = json.loads((carpeta / "manifest.json").read_text(encoding="utf-8"))
        archivo = carpeta / "pipeline.joblib"
        if hashlib.sha256(archivo.read_bytes()).hexdigest() != self.manifiesto["artefacto_sha256"]:
            raise RuntimeError(f"El hash de {archivo} no coincide con el manifiesto")
        self.pipeline = joblib.load(archivo)
        self.columnas = [f["nombre"] for f in self.manifiesto["features"]]
        self.umbral = float(self.manifiesto["umbral"])

    def predecir(self, features: dict) -> float:
        import pandas as pd

        df = pd.DataFrame([features])[self.columnas]
        return float(self.pipeline.predict_proba(df)[0, 1])

    def info(self) -> dict:
        m = self.manifiesto
        return {"model_version": self.version, "run_id": m.get("run_id"), "umbral": self.umbral,
                "features": m["features"], "clase_positiva": m["clase_positiva"],
                "metricas": m.get("metricas"), "dataset_sha256": m.get("dataset_sha256"),
                "promovido_en": self.activo.get("promovido_en"),
                # Promociones y rollbacks escritos por ml/scripts/promover.py (pantalla Modelo del admin)
                "historial": self.activo.get("historial", [])}
