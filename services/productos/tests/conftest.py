import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["DEMO_DATOS"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security import usuario_actual  # noqa: E402

ROL = {"rol": "admin"}


@pytest.fixture
def client():
    Base.metadata.create_all(engine)
    app.dependency_overrides[usuario_actual] = lambda: ROL
    ROL["rol"] = "admin"
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
