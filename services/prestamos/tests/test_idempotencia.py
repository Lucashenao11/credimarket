import pytest

from app.idempotencia import ConflictoIdempotencia, buscar_previa, hash_cuerpo
from app.models import ClaveIdempotencia
from tests.conftest import nuevo_prestamo


def test_el_orden_de_las_claves_no_cambia_el_hash():
    assert hash_cuerpo({"a": 1, "b": 2}) == hash_cuerpo({"b": 2, "a": 1})


def test_contenido_distinto_hash_distinto():
    assert hash_cuerpo({"producto_id": 1}) != hash_cuerpo({"producto_id": 2})


def test_el_hash_es_sha256_hexadecimal():
    h = hash_cuerpo({"a": 1})
    assert len(h) == 64 and int(h, 16) >= 0


def _registrar(db, cliente="CLI-1", clave="clave-123", cuerpo=None):
    p = nuevo_prestamo(db, cliente_id=cliente)
    db.add(ClaveIdempotencia(cliente_id=cliente, clave=clave,
                             hash_cuerpo=hash_cuerpo(cuerpo or {"x": 1}), prestamo_id=p.id))
    db.commit()
    return p


def test_clave_nueva_devuelve_none(db):
    assert buscar_previa(db, "CLI-1", "nueva-123", hash_cuerpo({"x": 1})) is None


def test_misma_clave_mismo_contenido_devuelve_el_mismo_prestamo(db):
    p = _registrar(db)
    assert buscar_previa(db, "CLI-1", "clave-123", hash_cuerpo({"x": 1})).id == p.id


def test_misma_clave_contenido_distinto_es_conflicto(db):
    _registrar(db)
    with pytest.raises(ConflictoIdempotencia):
        buscar_previa(db, "CLI-1", "clave-123", hash_cuerpo({"x": 2}))


def test_otro_cliente_con_la_misma_clave_no_ve_nada(db):
    _registrar(db)
    assert buscar_previa(db, "CLI-2", "clave-123", hash_cuerpo({"x": 2})) is None
