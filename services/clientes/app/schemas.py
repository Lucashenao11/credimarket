from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

TipoEmpleo = Literal["dependiente", "independiente", "temporal"]


class DatosFinancieros(BaseModel):
    """Rangos amplios pero razonables: rechazan valores imposibles, no perfiles de riesgo."""

    ingresos_mensuales_cop: float = Field(gt=0, le=1_000_000_000)
    obligaciones_mensuales_cop: float = Field(ge=0, le=1_000_000_000)
    tipo_empleo: TipoEmpleo | None = None  # faltante permitido
    antiguedad_laboral_meses: float | None = Field(default=None, ge=0, le=720)
    meses_historial_crediticio: float | None = Field(default=None, ge=0, le=720)
    creditos_previos: int = Field(ge=0, le=200)
    atrasos_previos_30d: int = Field(ge=0, le=200)
    porcentaje_pago_puntual: float | None = Field(default=None, ge=0, le=100)  # vacío si no hay historial


class ClienteCreate(DatosFinancieros):
    model_config = ConfigDict(extra="ignore")  # el CSV puede traer columnas que no son del cliente

    cliente_id: str = Field(pattern=r"^CLI-[A-Z0-9-]+$", max_length=30)
    nombre: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None


class ClienteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    activo: bool | None = None
    ingresos_mensuales_cop: float | None = Field(default=None, gt=0, le=1_000_000_000)
    obligaciones_mensuales_cop: float | None = Field(default=None, ge=0, le=1_000_000_000)
    tipo_empleo: TipoEmpleo | None = None
    antiguedad_laboral_meses: float | None = Field(default=None, ge=0, le=720)
    meses_historial_crediticio: float | None = Field(default=None, ge=0, le=720)
    creditos_previos: int | None = Field(default=None, ge=0, le=200)
    atrasos_previos_30d: int | None = Field(default=None, ge=0, le=200)
    porcentaje_pago_puntual: float | None = Field(default=None, ge=0, le=100)


class ClienteOut(DatosFinancieros):
    model_config = ConfigDict(from_attributes=True)

    cliente_id: str
    nombre: str | None
    email: str | None
    activo: bool
    creado_en: datetime | None
    actualizado_en: datetime | None


class ResultadoFila(BaseModel):
    fila: int  # número de línea en el archivo (la 1 es el encabezado)
    cliente_id: str | None
    resultado: Literal["insertado", "ya_existia", "error"]
    detalle: str | None = None


class ReporteImportacion(BaseModel):
    archivo: str
    total_filas: int
    insertados: int
    ya_existian: int
    errores: int
    filas: list[ResultadoFila]


class LoginIn(BaseModel):
    usuario: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    rol: str
    cliente_id: str | None
