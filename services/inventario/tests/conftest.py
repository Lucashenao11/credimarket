import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["DEMO_DATOS"] = "false"

import pytest  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import Existencia  # noqa: E402


@pytest.fixture
def db():
    Base.metadata.create_all(engine)
    sesion = SessionLocal()
    yield sesion
    sesion.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def bodega(db):
    """Producto 1 con 5 unidades y producto 2 con la última unidad."""
    db.add_all([Existencia(producto_id=1, disponible=5, reservado=0),
                Existencia(producto_id=2, disponible=1, reservado=0)])
    db.commit()
    return db
