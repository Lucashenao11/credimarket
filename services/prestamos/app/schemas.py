from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SolicitudIn(BaseModel):
    """Lo ÚNICO que decide el cliente. El monto, el precio y el cliente_id NO se aceptan."""
    model_config = ConfigDict(extra="forbid")

    producto_id: int = Field(gt=0)
    cantidad: int = Field(default=1, ge=1, le=5)
    plazo_meses: Literal[6, 12, 18, 24, 36]


class PrestamoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    cliente_id: str
    producto_id: int
    cantidad: int
    plazo_meses: int
    precio_unitario_cop: int
    version_cotizacion: int
    monto_cop: int
    cuota_cop: float
    probabilidad_incumplimiento: float | None
    modelo_version: str | None
    umbral: float | None
    estado: str
    motivo: str | None
    creado_en: datetime
    actualizado_en: datetime


class HistorialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    estado_anterior: str | None
    estado_nuevo: str
    motivo: str | None
    en: datetime


class RiesgoIn(BaseModel):
    ingresos_mensuales_cop: float
    obligaciones_mensuales_cop: float
    tipo_empleo: str | None = None
    antiguedad_laboral_meses: float | None = None
    meses_historial_crediticio: float | None = None
    creditos_previos: int
    atrasos_previos_30d: int
    porcentaje_pago_puntual: float | None = None
    monto_solicitado_cop: float
    plazo_meses: int
    cuota_estimada_cop: float
