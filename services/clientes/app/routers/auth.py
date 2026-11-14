from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Usuario
from ..schemas import LoginIn, TokenOut
from ..security import emitir_token, usuario_actual, verificar_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(datos: LoginIn, db: Session = Depends(get_db)):
    """Emite tokens de prueba de forma controlada: solo con el modo demo activo."""
    if not settings.demo_tokens_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Emisión de tokens deshabilitada")
    usuario = db.scalar(select(Usuario).where(Usuario.usuario == datos.usuario))
    if usuario is None or not verificar_password(datos.password, usuario.password_hash):
        # Mismo mensaje en ambos casos: no revelar qué usuarios existen
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o contraseña incorrectos")
    token, expira = emitir_token(usuario.usuario, usuario.rol, usuario.cliente_id)
    return TokenOut(access_token=token, expires_in=expira, rol=usuario.rol, cliente_id=usuario.cliente_id)


@router.get("/me")
def yo(usuario: dict = Depends(usuario_actual)):
    return usuario
