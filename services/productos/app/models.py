from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _ahora():
    return datetime.now(timezone.utc)


class Producto(Base):
    __tablename__ = "productos"
    __table_args__ = (CheckConstraint("precio_cop > 0", name="ck_precio_positivo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    categoria: Mapped[str] = mapped_column(String(60), nullable=False)
    precio_cop: Mapped[int] = mapped_column(Numeric(14, 0), nullable=False)
    # La versión sube en cada cambio. Préstamos guarda la versión cotizada.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora,
                                                     onupdate=_ahora)
