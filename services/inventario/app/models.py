from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Existencia(Base):
    """Unidades de un producto. Invariante: disponible + reservado = unidades físicas en bodega."""

    __tablename__ = "existencias"
    __table_args__ = (
        # Red de seguridad en la base de datos: aunque el código tuviera un error,
        # PostgreSQL rechazaría cualquier cambio que deje unidades negativas.
        CheckConstraint("disponible >= 0", name="ck_disponible_no_negativo"),
        CheckConstraint("reservado >= 0", name="ck_reservado_no_negativo"),
    )

    producto_id: Mapped[int] = mapped_column(Integer, primary_key=True)  # id del servicio Productos
    disponible: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reservado: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(),
                                                     onupdate=func.now())


class Reserva(Base):
    """Una reserva por préstamo. Estados: ACTIVA -> CONFIRMADA | LIBERADA | VENCIDA."""

    __tablename__ = "reservas"
    __table_args__ = (CheckConstraint("cantidad > 0", name="ck_cantidad_positiva"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # UNIQUE: un mismo préstamo nunca puede tener dos reservas, aunque el mensaje llegue dos veces
    prestamo_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    producto_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    motivo: Mapped[str | None] = mapped_column(String(60))
    vence_en: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    creada_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    actualizada_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(),
                                                     onupdate=func.now())


class Movimiento(Base):
    """Registro de solo inserción de todo lo que le pasa a las unidades (trazabilidad)."""

    __tablename__ = "movimientos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    producto_id: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    # ENTRADA | RESERVA | LIBERACION | VENCIMIENTO | SALIDA
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    prestamo_id: Mapped[str | None] = mapped_column(String(36))
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
