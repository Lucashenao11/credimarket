import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["DEMO_DATOS"] = "false"

import fakeredis  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.cache import CacheProductos  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security import usuario_actual  # noqa: E402

ROL = {"rol": "admin"}


@pytest.fixture
def redis_falso():
    """Redis en memoria (fakeredis): mismas operaciones y TTL que el real, sin servidor."""
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def cache(redis_falso):
    return CacheProductos(redis_falso, ttl_segundos=300)


@pytest.fixture
def client(cache):
    Base.metadata.create_all(engine)
    app.state.cache = cache
    app.dependency_overrides[usuario_actual] = lambda: ROL
    ROL["rol"] = "admin"
    yield TestClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
