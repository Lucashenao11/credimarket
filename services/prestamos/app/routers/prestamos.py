from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import eventos, solicitudes
from ..db import get_db
from ..idempotencia import ConflictoIdempotencia
from ..integraciones import Integraciones, get_integraciones
from ..models import HistorialEstado, Prestamo
from ..schemas import HistorialOut, PrestamoOut, SolicitudIn
from ..security import _bearer, requiere_rol, usuario_actual

router = APIRouter(tags=["prestamos"])


def get_modelo(request: Request):
    modelo = getattr(request.app.state, "modelo", None)
    if modelo is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "El modelo de riesgo no está cargado")
    return modelo


@router.post("/prestamos", response_model=PrestamoOut)
def crear(datos: SolicitudIn, response: Response,
          idempotency_key: str | None = Header(default=None, min_length=8, max_length=120),
          usuario: dict = Depends(requiere_rol("cliente")),
          cred: HTTPAuthorizationCredentials = Depends(_bearer),
          db: Session = Depends(get_db), integ: Integraciones = Depends(get_integraciones),
          modelo=Depends(get_modelo)):
    if idempotency_key is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Falta el encabezado Idempotency-Key (mínimo 8 caracteres)")
    # El cliente sale del token firmado, nunca del cuerpo de la petición.
    try:
        prestamo, repeticion = solicitudes.crear_solicitud(
            db, cred.credentials, usuario["cliente_id"], datos, idempotency_key, integ, modelo)
    except ConflictoIdempotencia:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Esa Idempotency-Key ya se usó con una solicitud distinta")
    if repeticion:
        response.headers["Idempotent-Replay"] = "true"
        response.status_code = status.HTTP_200_OK
    else:
        response.status_code = (status.HTTP_202_ACCEPTED if prestamo.estado == "PENDIENTE_INVENTARIO"
                                else status.HTTP_201_CREATED)
    return prestamo


def _visible(usuario: dict, prestamo: Prestamo | None) -> Prestamo:
    # Un cliente que pide el préstamo de otro recibe 404 (no se revela que existe)
    if prestamo is None or (usuario["rol"] != "admin" and prestamo.cliente_id != usuario.get("cliente_id")):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Préstamo no encontrado")
    return prestamo


@router.get("/prestamos", response_model=list[PrestamoOut])
def listar(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db),
           usuario: dict = Depends(usuario_actual)):
    consulta = select(Prestamo).order_by(Prestamo.creado_en.desc()).limit(limit)
    if usuario["rol"] != "admin":
        consulta = consulta.where(Prestamo.cliente_id == usuario.get("cliente_id"))
    return db.scalars(consulta).all()


@router.get("/prestamos/{prestamo_id}", response_model=PrestamoOut)
def consultar(prestamo_id: str, db: Session = Depends(get_db), usuario: dict = Depends(usuario_actual)):
    return _visible(usuario, db.get(Prestamo, prestamo_id))


@router.get("/prestamos/{prestamo_id}/historial", response_model=list[HistorialOut])
def historial(prestamo_id: str, db: Session = Depends(get_db), usuario: dict = Depends(usuario_actual)):
    _visible(usuario, db.get(Prestamo, prestamo_id))
    return db.scalars(select(HistorialEstado).where(HistorialEstado.prestamo_id == prestamo_id)
                      .order_by(HistorialEstado.id)).all()


@router.post("/prestamos/{prestamo_id}/cancelar", response_model=PrestamoOut)
def cancelar(prestamo_id: str, db: Session = Depends(get_db), usuario: dict = Depends(usuario_actual)):
    """Cancela antes de la entrega: el estado pasa a CANCELADA y se ordena liberar la reserva."""
    _visible(usuario, db.get(Prestamo, prestamo_id))
    if eventos.cancelar(db, prestamo_id) != "CANCELADA":
        raise HTTPException(status.HTTP_409_CONFLICT, "El préstamo ya no se puede cancelar")
    return db.get(Prestamo, prestamo_id, populate_existing=True)


@router.post("/prestamos/{prestamo_id}/entregar", status_code=202,
             dependencies=[Depends(requiere_rol("admin"))])
def entregar(prestamo_id: str, db: Session = Depends(get_db)):
    """Entrega simulada (solo administrador): ordena a Inventario confirmar la salida."""
    if db.get(Prestamo, prestamo_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Préstamo no encontrado")
    if eventos.solicitar_entrega(db, prestamo_id) != "ENTREGA_SOLICITADA":
        raise HTTPException(status.HTTP_409_CONFLICT, "Solo un préstamo APROBADO se puede entregar")
    return {"resultado": "ENTREGA_SOLICITADA"}
