"""Idempotency-Key: misma clave + mismo contenido -> la misma solicitud; contenido distinto -> 409."""

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ClaveIdempotencia, Prestamo


class ConflictoIdempotencia(Exception):
    pass


def hash_cuerpo(cuerpo: dict) -> str:
    """SHA-256 (hexadecimal) del cuerpo en forma canónica: mismas claves y valores -> mismo hash,
    sin importar el orden en que llegaron."""
    # TODO(Lucas) PIEZA 2a: json.dumps con sort_keys y separadores compactos -> encode -> sha256
    canonico = json.dumps(cuerpo, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonico.encode()).hexdigest()


def buscar_previa(
    db: Session, cliente_id: str, clave: str, hash_nuevo: str
) -> Prestamo | None:
    """None si la pareja (cliente_id, clave) es nueva. El préstamo anterior si el contenido es el mismo.
    Lanza ConflictoIdempotencia si la clave existe con contenido distinto."""
    # TODO(Lucas) PIEZA 2b: buscar la fila de ClaveIdempotencia por la PAREJA (cliente_id, clave)
    #   - no existe            -> return None
    #   - existe y hash igual  -> return el Prestamo de esa fila
    #   - existe y hash distinto -> raise ConflictoIdempotencia()
    fila = db.scalar(
        select(ClaveIdempotencia).where(
            ClaveIdempotencia.cliente_id == cliente_id, ClaveIdempotencia.clave == clave
        )
    )
    if fila is None:
        return None
    if fila.hash_cuerpo != hash_nuevo:
        raise ConflictoIdempotencia()
    return db.get(Prestamo, fila.prestamo_id)