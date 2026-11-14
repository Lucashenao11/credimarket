"""Emisión y validación de JWT RS256, y contraseñas de las cuentas de demostración."""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

# ---------- Contraseñas (scrypt de la librería estándar) ----------

def hash_password(password: str) -> str:
    sal = os.urandom(16)
    h = hashlib.scrypt(password.encode(), salt=sal, n=2**14, r=8, p=1)
    return f"scrypt${sal.hex()}${h.hex()}"


def verificar_password(password: str, almacenado: str) -> bool:
    try:
        _, sal_hex, h_hex = almacenado.split("$")
    except ValueError:
        return False
    h = hashlib.scrypt(password.encode(), salt=bytes.fromhex(sal_hex), n=2**14, r=8, p=1)
    return hmac.compare_digest(h.hex(), h_hex)  # comparación en tiempo constante


# ---------- Llaves ----------

@lru_cache
def _llave_privada() -> str:
    with open(settings.jwt_private_key_path) as f:
        return f.read()


@lru_cache
def _llave_publica() -> str:
    with open(settings.jwt_public_key_path) as f:
        return f.read()


# ---------- Tokens ----------

def emitir_token(sub: str, rol: str, cliente_id: str | None = None) -> tuple[str, int]:
    """Firma un token con la llave PRIVADA. Solo Clientes puede hacer esto."""
    ahora = datetime.now(timezone.utc)
    vida = timedelta(minutes=settings.jwt_ttl_minutes)
    payload = {
        "sub": sub,
        "rol": rol,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(ahora.timestamp()),
        "exp": int((ahora + vida).timestamp()),
    }
    if cliente_id:
        payload["cliente_id"] = cliente_id
    return jwt.encode(payload, _llave_privada(), algorithm="RS256"), int(vida.total_seconds())


def decodificar_token(token: str) -> dict:
    """Verifica la firma con la llave PÚBLICA, y además exp, iss y aud."""
    return jwt.decode(
        token,
        _llave_publica(),
        algorithms=["RS256"],  # nunca aceptar el algoritmo que diga el token
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )


_bearer = HTTPBearer(auto_error=False)


def usuario_actual(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    """401 si no hay token, si está vencido o si la firma no es válida."""
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta el token",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        return decodificar_token(cred.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión vencida",
                            headers={"WWW-Authenticate": "Bearer"})
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido",
                            headers={"WWW-Authenticate": "Bearer"})


def requiere_rol(*roles: str):
    """403 si el usuario está autenticado pero su rol no tiene permiso."""
    def _dependencia(usuario: dict = Depends(usuario_actual)) -> dict:
        if usuario.get("rol") not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para esta operación")
        return usuario
    return _dependencia
