"""Validación de JWT con la llave PÚBLICA. Inventario no puede emitir tokens."""
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings


@lru_cache
def _llave_publica() -> str:
    with open(settings.jwt_public_key_path) as f:
        return f.read()


_bearer = HTTPBearer(auto_error=False)


def usuario_actual(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    if cred is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta el token",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        return jwt.decode(cred.credentials, _llave_publica(), algorithms=["RS256"],
                          audience=settings.jwt_audience, issuer=settings.jwt_issuer)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión vencida",
                            headers={"WWW-Authenticate": "Bearer"})
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido",
                            headers={"WWW-Authenticate": "Bearer"})


def requiere_rol(*roles: str):
    def _dependencia(usuario: dict = Depends(usuario_actual)) -> dict:
        if usuario.get("rol") not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes permiso para esta operación")
        return usuario
    return _dependencia
