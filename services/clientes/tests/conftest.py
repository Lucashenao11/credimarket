import os

# Las pruebas usan una base SQLite en memoria: no tocan la base real del servicio.
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["DEMO_TOKENS_ENABLED"] = "false"

import pytest  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402


@pytest.fixture
def db():
    Base.metadata.create_all(engine)
    sesion = SessionLocal()
    yield sesion
    sesion.close()
    Base.metadata.drop_all(engine)
