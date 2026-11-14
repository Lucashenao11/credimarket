from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExistenciaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    producto_id: int
    disponible: int
    reservado: int
    actualizado_en: datetime | None


class EntradaIn(BaseModel):
    cantidad: int = Field(gt=0, le=100_000)


class ReservaIn(BaseModel):
    prestamo_id: str = Field(min_length=1, max_length=36)
    producto_id: int = Field(gt=0)
    cantidad: int = Field(gt=0, le=1000)


class ReservaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    prestamo_id: str
    producto_id: int
    cantidad: int
    estado: str
    motivo: str | None
    vence_en: datetime
    creada_en: datetime | None


class MovimientoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    producto_id: int
    tipo: str
    cantidad: int
    prestamo_id: str | None
    creado_en: datetime | None


class ResultadoOperacion(BaseModel):
    prestamo_id: str
    resultado: str
