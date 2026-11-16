"""Caso de uso: crear una solicitud de préstamo (pasos 1 a 5 del enunciado)."""
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import estados
from .config import settings
from .idempotencia import buscar_previa, hash_cuerpo
from .integraciones import Integraciones
from .models import ClaveIdempotencia, HistorialEstado, Prestamo
from .reglas import motivo_de_rechazo
from .riesgo import calcular_cuota, construir_features
from .schemas import SolicitudIn


def crear_solicitud(db: Session, token: str, cliente_id: str, datos: SolicitudIn, clave: str,
                    integ: Integraciones, modelo) -> tuple[Prestamo, bool]:
    """Devuelve (préstamo, es_repetición). es_repetición=True si la clave ya se había usado."""
    huella = hash_cuerpo(datos.model_dump())

    previa = buscar_previa(db, cliente_id, clave, huella)  # puede lanzar ConflictoIdempotencia
    if previa is not None:
        return previa, True

    # Recolección de datos: el precio sale de la cotización, nunca del cliente
    cliente = integ.obtener_cliente(token, cliente_id)
    cotizacion = integ.obtener_cotizacion(token, datos.producto_id)
    if not cotizacion["activo"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "El producto está desactivado")

    monto = cotizacion["precio_cop"] * datos.cantidad
    features = construir_features(cliente, monto, datos.plazo_meses, settings.tasa_mensual)
    probabilidad = modelo.predecir(features)
    motivo = motivo_de_rechazo(cliente, monto, probabilidad, modelo.umbral)
    estado = estados.RECHAZADA if motivo else estados.PENDIENTE_INVENTARIO

    prestamo = Prestamo(
        cliente_id=cliente_id, producto_id=datos.producto_id, cantidad=datos.cantidad,
        plazo_meses=datos.plazo_meses, precio_unitario_cop=cotizacion["precio_cop"],
        version_cotizacion=cotizacion["version"], monto_cop=monto,
        cuota_cop=round(features["cuota_estimada_cop"], 2),
        probabilidad_incumplimiento=round(probabilidad, 6), modelo_version=modelo.version,
        umbral=modelo.umbral, estado=estado, motivo=motivo)
    db.add(prestamo)
    db.flush()  # asigna el id
    db.add(HistorialEstado(prestamo_id=prestamo.id, estado_anterior=None, estado_nuevo=estado,
                           motivo=motivo))
    db.add(ClaveIdempotencia(cliente_id=cliente_id, clave=clave, hash_cuerpo=huella,
                             prestamo_id=prestamo.id))
    # TODO(broker, martes): si estado == PENDIENTE_INVENTARIO, insertar ReservaSolicitada en el
    # outbox DENTRO de esta misma transacción (así no puede haber préstamo sin comando ni al revés).
    try:
        db.commit()
    except IntegrityError:
        # Otra petición con la misma clave ganó la carrera: devolvemos la suya.
        db.rollback()
        previa = buscar_previa(db, cliente_id, clave, huella)
        if previa is None:
            raise
        return previa, True
    return prestamo, False
