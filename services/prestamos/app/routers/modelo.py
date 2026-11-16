from fastapi import APIRouter, Depends

from ..reglas import motivo_de_rechazo  # noqa: F401  (reservado para la regla de /riesgo/predict)
from ..schemas import RiesgoIn
from ..security import requiere_rol, usuario_actual
from .prestamos import get_modelo

router = APIRouter(tags=["modelo"])


@router.get("/modelo/info", dependencies=[Depends(usuario_actual)])
def info(modelo=Depends(get_modelo)):
    return modelo.info()


@router.post("/riesgo/predict", dependencies=[Depends(requiere_rol("admin"))])
def predecir(datos: RiesgoIn, modelo=Depends(get_modelo)):
    """Prueba el pipeline con características dadas. No crea préstamos ni reserva inventario."""
    p = modelo.predecir(datos.model_dump())
    return {"probabilidad_incumplimiento": p, "umbral": modelo.umbral,
            "decision": "RIESGO_ALTO" if p >= modelo.umbral else "FAVORABLE",
            "model_version": modelo.version}
