"""Pruebas de la importación CSV idempotente (prueba de aceptación 12).

Ejecutar dentro del contenedor:
    docker compose exec clientes pytest -v
"""
from sqlalchemy import func, select

from app.importacion import importar_csv, insertar_si_no_existe
from app.models import Cliente
from app.schemas import ClienteCreate

ENCABEZADO = (
    "cliente_id,ingresos_mensuales_cop,obligaciones_mensuales_cop,tipo_empleo,"
    "antiguedad_laboral_meses,meses_historial_crediticio,creditos_previos,"
    "atrasos_previos_30d,porcentaje_pago_puntual\n"
)
VALIDAS = (
    "CLI-0000001,2757000,1059000,dependiente,6.0000,54.0000,0,0,\n"
    "CLI-0000002,1753000,825000,dependiente,1.0000,105.0000,6,0,92.98\n"
    "CLI-0000003,3755000,893000,,22.0000,97.0000,9,8,67.45\n"
)


def _csv(cuerpo: str) -> bytes:
    return (ENCABEZADO + cuerpo).encode("utf-8")


def _contar(db) -> int:
    return db.scalar(select(func.count()).select_from(Cliente))


def test_insertar_si_no_existe_dos_veces(db):
    datos = ClienteCreate(cliente_id="CLI-TEST-1", ingresos_mensuales_cop=2_000_000,
                          obligaciones_mensuales_cop=300_000, creditos_previos=1,
                          atrasos_previos_30d=0)
    assert insertar_si_no_existe(db, datos) == "insertado"
    assert insertar_si_no_existe(db, datos) == "ya_existia"
    assert _contar(db) == 1


def test_primera_importacion_inserta_todo(db):
    reporte = importar_csv(db, _csv(VALIDAS), "clientes.csv")
    assert (reporte.insertados, reporte.ya_existian, reporte.errores) == (3, 0, 0)
    assert _contar(db) == 3


def test_importar_dos_veces_no_duplica(db):
    importar_csv(db, _csv(VALIDAS), "clientes.csv")
    segunda = importar_csv(db, _csv(VALIDAS), "clientes.csv")
    assert (segunda.insertados, segunda.ya_existian, segunda.errores) == (0, 3, 0)
    assert _contar(db) == 3


def test_fila_invalida_no_detiene_las_demas(db):
    cuerpo = (
        "CLI-0000001,2757000,1059000,dependiente,6,54,0,0,\n"
        "CLI-0000002,-5,825000,dependiente,1,105,6,0,92.98\n"       # ingresos negativos
        "CLI-0000003,3755000,893000,pensionado,22,97,9,8,67.45\n"   # tipo de empleo no permitido
        "CLI-0000004,3000000,500000,temporal,10,20,1,0,90\n"
    )
    reporte = importar_csv(db, _csv(cuerpo), "con_errores.csv")
    assert (reporte.insertados, reporte.errores) == (2, 2)
    errores = [f for f in reporte.filas if f.resultado == "error"]
    assert [f.fila for f in errores] == [3, 4]  # números de línea en el archivo
    assert "ingresos_mensuales_cop" in errores[0].detalle
    assert _contar(db) == 2


def test_clave_repetida_dentro_del_mismo_archivo(db):
    cuerpo = (
        "CLI-0000001,2757000,1059000,dependiente,6,54,0,0,\n"
        "CLI-0000001,9999999,1,independiente,1,1,1,1,1\n"
    )
    reporte = importar_csv(db, _csv(cuerpo), "repetido.csv")
    assert (reporte.insertados, reporte.ya_existian) == (1, 1)
    # La política es "solo insertar": la segunda fila no modificó la primera
    assert db.scalar(select(Cliente.ingresos_mensuales_cop)) == 2757000
