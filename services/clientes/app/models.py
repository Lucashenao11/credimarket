from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Clave externa estable (la del CSV). La restricción UNIQUE es la que impide duplicados,
    # incluso si dos importaciones corren al mismo tiempo.
    cliente_id: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)

    nombre: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(160))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Información financiera y laboral (las mismas variables del histórico)
    ingresos_mensuales_cop: Mapped[float] = mapped_column(Float, nullable=False)
    obligaciones_mensuales_cop: Mapped[float] = mapped_column(Float, nullable=False)
    tipo_empleo: Mapped[str | None] = mapped_column(String(20))
    antiguedad_laboral_meses: Mapped[float | None] = mapped_column(Float)
    meses_historial_crediticio: Mapped[float | None] = mapped_column(Float)
    creditos_previos: Mapped[int] = mapped_column(Integer, nullable=False)
    atrasos_previos_30d: Mapped[int] = mapped_column(Integer, nullable=False)
    porcentaje_pago_puntual: Mapped[float | None] = mapped_column(Float)

    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Usuario(Base):
    """Cuentas de acceso. En esta versión solo existen las cuentas de demostración."""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    rol: Mapped[str] = mapped_column(String(20), nullable=False)  # "cliente" o "admin"
    cliente_id: Mapped[str | None] = mapped_column(String(30))  # solo para rol "cliente"
