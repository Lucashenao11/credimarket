from tests.conftest import ROL

NUEVO = {"nombre": "Portátil X", "categoria": "computadores", "precio_cop": 3_000_000}


def test_crear_y_consultar(client):
    r = client.post("/productos", json=NUEVO)
    assert r.status_code == 201 and r.json()["version"] == 1
    assert client.get(f"/productos/{r.json()['id']}").json()["nombre"] == "Portátil X"


def test_actualizar_sube_version(client):
    pid = client.post("/productos", json=NUEVO).json()["id"]
    r = client.put(f"/productos/{pid}", json={"precio_cop": 3_200_000})
    assert r.json()["version"] == 2 and r.json()["precio_cop"] == 3_200_000


def test_desactivar_y_cotizacion(client):
    pid = client.post("/productos", json=NUEVO).json()["id"]
    client.delete(f"/productos/{pid}")
    c = client.get(f"/productos/{pid}/cotizacion").json()
    assert c["activo"] is False and c["version"] == 2
    assert pid not in [p["id"] for p in client.get("/productos").json()]


def test_cliente_no_puede_crear_pero_si_cotizar(client):
    pid = client.post("/productos", json=NUEVO).json()["id"]
    ROL["rol"] = "cliente"
    assert client.post("/productos", json=NUEVO).status_code == 403
    assert client.get(f"/productos/{pid}/cotizacion").status_code == 200


def test_inexistente_404(client):
    assert client.get("/productos/999").status_code == 404
