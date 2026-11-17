from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductoIn(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    categoria: str = Field(min_length=2, max_length=60)
    precio_cop: int = Field(gt=0)


class ProductoUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=2, max_length=120)
    categoria: str | None = Field(default=None, min_length=2, max_length=60)
    precio_cop: int | None = Field(default=None, gt=0)
    # Permite REACTIVAR un producto desactivado (DELETE solo desactiva). Cuenta como cambio: sube la versión.
    activo: bool | None = None


class ProductoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    categoria: str
    precio_cop: int
    version: int
    activo: bool


class CotizacionOut(BaseModel):
    producto_id: int
    nombre: str
    precio_cop: int
    version: int
    activo: bool
    consultado_en: datetime
