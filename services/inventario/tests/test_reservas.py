"""Pruebas de la lógica de Inventario.

Ejecutar dentro del contenedor:
    docker compose exec inventario pytest -v
"""
from datetime import timedelta

from sqlalchemy import func, select

from app.models import Existencia, Movimiento, Reserva
from app.reservas import ahora_utc, confirmar_salida, liberar, reservar, vencer_reservas


def _stock(db, producto_id):
    e = db.get(Existencia, producto_id, populate_existing=True)
    return (e.disponible, e.reservado)


def _reserva(db, prestamo_id):
    return db.scalar(select(Reserva).where(Reserva.prestamo_id == prestamo_id)
                     .execution_options(populate_existing=True))


def _contar(db, modelo):
    return db.scalar(select(func.count()).select_from(modelo))


# ---------------- reservar ----------------

def test_reservar_con_unidades(bodega):
    assert reservar(bodega, "P-1", producto_id=1, cantidad=2) == "RESERVADA"
    assert _stock(bodega, 1) == (3, 2)
    r = _reserva(bodega, "P-1")
    assert (r.estado, r.cantidad, r.producto_id) == ("ACTIVA", 2, 1)
    assert r.vence_en > ahora_utc()
    assert bodega.scalar(select(Movimiento.tipo).where(Movimiento.prestamo_id == "P-1")) == "RESERVA"


def test_reservar_sin_unidades_suficientes(bodega):
    """Prueba de aceptación 3: no hay reserva y el stock no queda negativo."""
    assert reservar(bodega, "P-1", producto_id=1, cantidad=6) == "INSUFICIENTE"
    assert _stock(bodega, 1) == (5, 0)
    assert _contar(bodega, Reserva) == 0


def test_reservar_producto_sin_existencias(bodega):
    assert reservar(bodega, "P-1", producto_id=99, cantidad=1) == "INSUFICIENTE"
    assert _contar(bodega, Reserva) == 0


def test_dos_prestamos_por_la_ultima_unidad(bodega):
    """Prueba de aceptación 4 (versión secuencial; la concurrente está en el script de demo)."""
    resultados = [reservar(bodega, "P-A", 2, 1), reservar(bodega, "P-B", 2, 1)]
    assert sorted(resultados) == ["INSUFICIENTE", "RESERVADA"]
    assert _stock(bodega, 2) == (0, 1)


def test_mismo_prestamo_dos_veces(bodega):
    """Prueba de aceptación 5: un mensaje repetido no descuenta las unidades dos veces."""
    assert reservar(bodega, "P-1", 1, 2) == "RESERVADA"
    assert reservar(bodega, "P-1", 1, 2) == "YA_PROCESADA"
    assert _stock(bodega, 1) == (3, 2)
    assert _contar(bodega, Reserva) == 1


def test_mismo_prestamo_dos_veces_con_la_ultima_unidad(bodega):
    """El mensaje repetido llega cuando ya no queda stock: debe decir YA_PROCESADA, no INSUFICIENTE.

    Si respondiera INSUFICIENTE, el consumidor publicaría InventarioInsuficiente para un
    préstamo que sí tiene su reserva.
    """
    assert reservar(bodega, "P-1", producto_id=2, cantidad=1) == "RESERVADA"
    assert reservar(bodega, "P-1", producto_id=2, cantidad=1) == "YA_PROCESADA"
    assert _stock(bodega, 2) == (0, 1)
    assert _contar(bodega, Reserva) == 1


# ---------------- liberar ----------------

def test_liberar_devuelve_unidades(bodega):
    reservar(bodega, "P-1", 1, 2)
    assert liberar(bodega, "P-1", motivo="CANCELADA") == "LIBERADA"
    assert _stock(bodega, 1) == (5, 0)
    r = _reserva(bodega, "P-1")
    assert (r.estado, r.motivo) == ("LIBERADA", "CANCELADA")
    tipos = bodega.scalars(select(Movimiento.tipo).where(Movimiento.prestamo_id == "P-1")).all()
    assert sorted(tipos) == ["LIBERACION", "RESERVA"]


def test_liberar_dos_veces(bodega):
    """Prueba de aceptación 7: un evento repetido no devuelve las unidades dos veces."""
    reservar(bodega, "P-1", 1, 2)
    assert liberar(bodega, "P-1") == "LIBERADA"
    assert liberar(bodega, "P-1") == "YA_FINALIZADA"
    assert _stock(bodega, 1) == (5, 0)


def test_liberar_reserva_inexistente(bodega):
    assert liberar(bodega, "NO-EXISTE") == "NO_EXISTE"


# ---------------- confirmar salida (ya implementada) ----------------

def test_confirmar_salida_y_luego_liberar(bodega):
    reservar(bodega, "P-1", 1, 2)
    assert confirmar_salida(bodega, "P-1") == "CONFIRMADA"
    assert _stock(bodega, 1) == (3, 0)  # las 2 unidades salieron de la bodega
    # Una cancelación tardía no puede devolver unidades que ya se entregaron
    assert liberar(bodega, "P-1") == "YA_FINALIZADA"
    assert _stock(bodega, 1) == (3, 0)


# ---------------- vencimiento (ya implementado; usa tu liberar) ----------------

def test_vencer_reservas(bodega):
    reservar(bodega, "P-1", 1, 2)
    reservar(bodega, "P-2", 1, 1)
    futuro = ahora_utc() + timedelta(days=1)
    assert sorted(vencer_reservas(bodega, ahora=futuro)) == ["P-1", "P-2"]
    assert _stock(bodega, 1) == (5, 0)
    r = _reserva(bodega, "P-1")
    assert (r.estado, r.motivo) == ("VENCIDA", "RESERVA_VENCIDA")
    assert vencer_reservas(bodega, ahora=futuro) == []  # nada más que vencer


# ---------------- invariante ----------------

def test_invariante_unidades_fisicas(bodega):
    """disponible + reservado = unidades físicas, después de cualquier secuencia de operaciones."""
    reservar(bodega, "P-1", 1, 2)
    reservar(bodega, "P-2", 1, 3)
    reservar(bodega, "P-3", 1, 1)        # insuficiente: quedan 0
    liberar(bodega, "P-1")
    confirmar_salida(bodega, "P-2")      # salen 3 unidades físicas
    disponible, reservado = _stock(bodega, 1)
    assert disponible + reservado == 5 - 3
    assert disponible >= 0 and reservado >= 0