from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..importacion import importar_csv
from ..models import Cliente
from ..schemas import ClienteCreate, ClienteOut, ClienteUpdate, ReporteImportacion
from ..security import requiere_rol, usuario_actual

router = APIRouter(prefix="/clientes", tags=["clientes"])

CAMPOS_EDITABLES_POR_CLIENTE = {"nombre", "email"}


def _obtener(db: Session, cliente_id: str) -> Cliente:
    cliente = db.scalar(select(Cliente).where(Cliente.cliente_id == cliente_id))
    if cliente is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cliente no encontrado")
    return cliente


def _puede_ver(usuario: dict, cliente_id: str) -> bool:
    # Un cliente solo accede a sus propios datos; el cliente_id sale del token firmado,
    # no de algo que el cliente envíe en la petición.
    return usuario["rol"] == "admin" or usuario.get("cliente_id") == cliente_id


@router.post("", response_model=ClienteOut, status_code=status.HTTP_201_CREATED)
def crear(datos: ClienteCreate, db: Session = Depends(get_db),
          _: dict = Depends(requiere_rol("admin"))):
    cliente = Cliente(**datos.model_dump())
    db.add(cliente)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"Ya existe el cliente {datos.cliente_id}")
    return cliente


@router.get("", response_model=list[ClienteOut])
def listar(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
           db: Session = Depends(get_db), _: dict = Depends(requiere_rol("admin"))):
    return db.scalars(select(Cliente).order_by(Cliente.id).limit(limit).offset(offset)).all()


@router.post("/importar", response_model=ReporteImportacion)
async def importar(archivo: UploadFile, db: Session = Depends(get_db),
                   _: dict = Depends(requiere_rol("admin"))):
    contenido = await archivo.read()
    try:
        return importar_csv(db, contenido, archivo.filename or "archivo.csv")
    except (ValueError, UnicodeDecodeError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Archivo inválido: {e}")


@router.get("/{cliente_id}", response_model=ClienteOut)
def consultar(cliente_id: str, db: Session = Depends(get_db),
              usuario: dict = Depends(usuario_actual)):
    if not _puede_ver(usuario, cliente_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No puedes consultar otro cliente")
    return _obtener(db, cliente_id)


@router.patch("/{cliente_id}", response_model=ClienteOut)
def actualizar(cliente_id: str, cambios: ClienteUpdate, db: Session = Depends(get_db),
               usuario: dict = Depends(usuario_actual)):
    if not _puede_ver(usuario, cliente_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No puedes modificar otro cliente")
    datos = cambios.model_dump(exclude_unset=True)
    if usuario["rol"] != "admin" and not set(datos) <= CAMPOS_EDITABLES_POR_CLIENTE:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Un cliente solo puede editar su nombre y su correo")
    cliente = _obtener(db, cliente_id)
    for campo, valor in datos.items():
        setattr(cliente, campo, valor)
    db.commit()
    return cliente
