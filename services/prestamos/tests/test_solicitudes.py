from sqlalchemy import func, select

from app.models import Prestamo
from tests.conftest import USUARIO, nuevo_prestamo

CUERPO = {"producto_id": 1, "cantidad": 1, "plazo_meses": 12}


def _post(client, cuerpo=CUERPO, clave="clave-0001"):
    return client.post("/prestamos", json=cuerpo, headers={"Idempotency-Key": clave})


def test_solicitud_favorable_queda_pendiente_con_202(client):
    r = _post(client)
    assert r.status_code == 202
    j = r.json()
    assert j["estado"] == "PENDIENTE_INVENTARIO" and j["cliente_id"] == "CLI-1"
    # el monto sale de la cotización de Productos, no del cliente
    assert j["monto_cop"] == 2_800_000 and j["version_cotizacion"] == 3
    assert j["modelo_version"] == "fake-1" and j["cuota_cop"] > 0


def test_el_cliente_no_puede_enviar_monto_ni_cliente_id(client):
    assert _post(client, {**CUERPO, "monto_cop": 1}).status_code == 422
    assert _post(client, {**CUERPO, "cliente_id": "CLI-9"}).status_code == 422


def test_riesgo_alto_se_rechaza_y_no_pide_inventario(client, modelo):
    modelo.probabilidad = 0.9
    r = _post(client)
    assert r.status_code == 201
    assert r.json()["estado"] == "RECHAZADA" and r.json()["motivo"] == "RIESGO_ALTO"


def test_cliente_inactivo_se_rechaza(client, integ):
    integ.cliente["activo"] = False
    assert _post(client).json()["motivo"] == "CLIENTE_INACTIVO"


def test_monto_fuera_de_rango_se_rechaza(client, integ):
    integ.cotizacion["precio_cop"] = 9_000_000
    r = _post(client, {**CUERPO, "cantidad": 3})  # 27 millones
    assert r.json()["estado"] == "RECHAZADA" and r.json()["motivo"] == "MONTO_FUERA_DE_RANGO"


def test_producto_desactivado_da_422_y_no_crea_prestamo(client, integ, db):
    integ.cotizacion["activo"] = False
    assert _post(client).status_code == 422
    assert db.scalar(select(func.count()).select_from(Prestamo)) == 0


def test_falta_la_clave_de_idempotencia(client):
    assert client.post("/prestamos", json=CUERPO).status_code == 400


def test_solo_el_rol_cliente_solicita(client):
    USUARIO["rol"] = "admin"
    assert _post(client).status_code == 403


def test_repetir_la_peticion_devuelve_el_mismo_prestamo_sin_duplicar(client, db, integ):
    r1 = _post(client)
    llamadas = integ.llamadas
    r2 = _post(client)
    assert r2.status_code == 200 and r2.headers["Idempotent-Replay"] == "true"
    assert r2.json()["id"] == r1.json()["id"]
    assert integ.llamadas == llamadas  # la repetición no vuelve a consultar a nadie
    assert db.scalar(select(func.count()).select_from(Prestamo)) == 1


def test_misma_clave_con_contenido_distinto_da_409(client):
    _post(client)
    assert _post(client, {**CUERPO, "plazo_meses": 24}).status_code == 409


def test_dos_clientes_pueden_usar_la_misma_clave(client):
    a = _post(client).json()
    USUARIO["cliente_id"] = "CLI-2"
    b = _post(client)
    assert b.status_code == 202 and b.json()["id"] != a["id"]


def test_un_cliente_no_ve_el_prestamo_de_otro(client, db):
    p = nuevo_prestamo(db, cliente_id="CLI-2")
    assert client.get(f"/prestamos/{p.id}").status_code == 404
    USUARIO["rol"] = "admin"
    assert client.get(f"/prestamos/{p.id}").status_code == 200


def test_listar_solo_los_propios(client, db):
    nuevo_prestamo(db, cliente_id="CLI-1")
    nuevo_prestamo(db, cliente_id="CLI-2")
    assert [p["cliente_id"] for p in client.get("/prestamos").json()] == ["CLI-1"]


def test_sin_modelo_responde_503(client):
    from app.main import app
    app.state.modelo = None
    assert _post(client).status_code == 503
