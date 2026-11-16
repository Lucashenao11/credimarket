import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _ahora():
    return datetime.now(timezone.utc)


def _uuid():
    return str(uuid.uuid4())


class Prestamo(Base):
    __tablename__ = "prestamos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)  # identificador consultable
    cliente_id: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    producto_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    plazo_meses: Mapped[int] = mapped_column(Integer, nullable=False)

    # Lo que se usó para decidir: el precio y la versión de la cotización (nunca los envía el cliente)
    precio_unitario_cop: Mapped[int] = mapped_column(Integer, nullable=False)
    version_cotizacion: Mapped[int] = mapped_column(Integer, nullable=False)
    monto_cop: Mapped[int] = mapped_column(Integer, nullable=False)
    cuota_cop: Mapped[float] = mapped_column(Float, nullable=False)

    probabilidad_incumplimiento: Mapped[float | None] = mapped_column(Float)
    modelo_version: Mapped[str | None] = mapped_column(String(60))
    umbral: Mapped[float | None] = mapped_column(Float)

    estado: Mapped[str] = mapped_column(String(30), nullable=False)
    motivo: Mapped[str | None] = mapped_column(String(60))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora, onupdate=_ahora)


class HistorialEstado(Base):
    __tablename__ = "historial_estados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prestamo_id: Mapped[str] = mapped_column(ForeignKey("prestamos.id"), nullable=False, index=True)
    estado_anterior: Mapped[str | None] = mapped_column(String(30))
    estado_nuevo: Mapped[str] = mapped_column(String(30), nullable=False)
    motivo: Mapped[str | None] = mapped_column(String(60))
    en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)


class ClaveIdempotencia(Base):
    __tablename__ = "claves_idempotencia"
    # La unicidad vive en la base de datos, no en memoria: es la que gana la carrera entre
    # dos peticiones simultáneas con la misma clave.
    __table_args__ = (UniqueConstraint("cliente_id", "clave", name="uq_cliente_clave"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cliente_id: Mapped[str] = mapped_column(String(30), nullable=False)
    clave: Mapped[str] = mapped_column(String(120), nullable=False)
    hash_cuerpo: Mapped[str] = mapped_column(String(64), nullable=False)
    prestamo_id: Mapped[str] = mapped_column(ForeignKey("prestamos.id"), nullable=False)
