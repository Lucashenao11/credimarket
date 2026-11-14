"""Importación masiva de clientes desde CSV.

Política (decidida por Lucas):
- Clave externa única: cliente_id.
- Si el cliente_id ya existe, la fila NO se modifica y se reporta como "ya_existia".
- Una fila con errores se rechaza sola; las demás se procesan igual.

Cada fila es su propia transacción: así, una fila que falla no deshace las que ya se guardaron.
"""
import csv
import io

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError  # noqa: F401  (la vas a necesitar en el TODO)
from sqlalchemy.orm import Session

from .models import Cliente  # noqa: F401  (la vas a necesitar en el TODO)
from .schemas import ClienteCreate, ReporteImportacion, ResultadoFila


def insertar_si_no_existe(db: Session, datos: ClienteCreate) -> str:
    """Guarda un cliente nuevo. Devuelve "insertado" o "ya_existia".

    TODO(Lucas): escribe esta función (unas 8 líneas).

    Requisitos:
      1. Si el cliente_id NO existe: guardarlo y devolver "insertado".
      2. Si el cliente_id YA existe: no modificar nada y devolver "ya_existia".
      3. Debe ser correcto aunque dos importaciones del mismo archivo corran al mismo tiempo.

    Piezas que tienes:
      - Cliente(**datos.model_dump()) crea el objeto a partir de los datos validados.
      - db.add(objeto) y db.commit() lo guardan.
      - Si la restricción UNIQUE de cliente_id se viola, db.commit() lanza IntegrityError.
      - Después de un IntegrityError, la sesión queda inservible hasta llamar db.rollback().

    Pregunta antes de escribir: ¿por qué NO conviene hacer primero un SELECT para preguntar
    si el cliente_id existe, y después el INSERT? (Recuerda el nickname y "beto").
    """
    nuevo_cliente = Cliente(**datos.model_dump())
    db.add(nuevo_cliente)
    try:
        db.commit()
        return "insertado"
    except IntegrityError:
        db.rollback()
        return "ya_existia"


def _limpiar(fila: dict[str, str]) -> dict[str, str | None]:
    """Convierte las celdas vacías en None (faltantes) y quita espacios."""
    return {
        (k or "").strip(): (v.strip() if isinstance(v, str) and v.strip() != "" else None)
        for k, v in fila.items()
    }


def _resumir_error(e: ValidationError) -> str:
    partes = []
    for err in e.errors():
        campo = ".".join(str(x) for x in err["loc"]) or "fila"
        partes.append(f"{campo}: {err['msg']}")
    return "; ".join(partes)


def importar_csv(db: Session, contenido: bytes, nombre_archivo: str) -> ReporteImportacion:
    texto = contenido.decode("utf-8-sig")  # tolera el BOM que agrega Excel
    lector = csv.DictReader(io.StringIO(texto))
    if not lector.fieldnames or "cliente_id" not in [c.strip() for c in lector.fieldnames]:
        raise ValueError("El archivo debe tener encabezado y una columna cliente_id")

    filas: list[ResultadoFila] = []
    for numero, fila_cruda in enumerate(lector, start=2):  # la línea 1 es el encabezado
        fila = _limpiar(fila_cruda)
        cliente_id = fila.get("cliente_id")
        try:
            datos = ClienteCreate.model_validate(fila)
        except ValidationError as e:
            filas.append(ResultadoFila(fila=numero, cliente_id=cliente_id, resultado="error",
                                       detalle=_resumir_error(e)))
            continue

        resultado = insertar_si_no_existe(db, datos)
        filas.append(ResultadoFila(fila=numero, cliente_id=datos.cliente_id, resultado=resultado))

    return ReporteImportacion(
        archivo=nombre_archivo,
        total_filas=len(filas),
        insertados=sum(f.resultado == "insertado" for f in filas),
        ya_existian=sum(f.resultado == "ya_existia" for f in filas),
        errores=sum(f.resultado == "error" for f in filas),
        filas=filas,
    )
