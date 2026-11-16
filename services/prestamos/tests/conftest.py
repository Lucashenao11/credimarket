import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.integraciones import get_integraciones  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Prestamo  # noqa: E402
from app.security import usuario_actual  # noqa: E402

CLIENTE_OK = {
    "cliente_id": "CLI-1", "activo": True, "ingresos_mensuales_cop": 4_000_000,
    "obligaciones_mensuales_cop": 500_000, "tipo_empleo": "dependiente",
    "antiguedad_laboral_meses": 24.0, "meses_historial_crediticio": 60.0,
    "creditos_previos": 2, "atrasos_previos_30d": 0, "porcentaje_pago_puntual": 95.0,
}


class FakeIntegraciones:
    def __init__(self):
        self.cliente = dict(CLIENTE_OK)
        self.cotizacion = {"producto_id": 1, "nombre": "Portátil", "precio_cop": 2_800_000,
                           "version": 3, "activo": True, "consultado_en": "2026-11-16T00:00:00Z"}
        self.llamadas = 0

    def obtener_cliente(self, token, cliente_id):
        self.llamadas += 1
        return {**self.cliente, "cliente_id": cliente_id}

    def obtener_cotizacion(self, token, producto_id):
        self.llamadas += 1
        return self.cotizacion


class FakeModelo:
    version = "fake-1"
    umbral = 0.5

    def __init__(self):
        self.probabilidad = 0.1

    def predecir(self, features):
        return self.probabilidad

    def info(self):
        return {"model_version": self.version, "umbral": self.umbral}


USUARIO = {}


@pytest.fixture
def db():
    Base.metadata.create_all(engine)
    s = SessionLocal()
    yield s
    s.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def integ():
    return FakeIntegraciones()


@pytest.fixture
def modelo():
    return FakeModelo()


@pytest.fixture
def client(db, integ, modelo):
    app.state.modelo = modelo
    app.dependency_overrides[usuario_actual] = lambda: USUARIO
    app.dependency_overrides[get_integraciones] = lambda: integ
    USUARIO.clear()
    USUARIO.update({"sub": "ana", "rol": "cliente", "cliente_id": "CLI-1"})
    yield TestClient(app, headers={"Authorization": "Bearer token-de-prueba"})
    app.dependency_overrides.clear()
    app.state.modelo = None


def nuevo_prestamo(db, estado="PENDIENTE_INVENTARIO", cliente_id="CLI-1"):
    p = Prestamo(cliente_id=cliente_id, producto_id=1, cantidad=1, plazo_meses=12,
                 precio_unitario_cop=2_800_000, version_cotizacion=1, monto_cop=2_800_000,
                 cuota_cop=260_000.0, estado=estado)
    db.add(p)
    db.commit()
    return p
