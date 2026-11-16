from .config import settings


def motivo_de_rechazo(cliente: dict, monto: int, probabilidad: float, umbral: float) -> str | None:
    """None = favorable. Si no, el motivo con el que la solicitud queda RECHAZADA."""
    if not cliente.get("activo", False):
        return "CLIENTE_INACTIVO"
    if cliente.get("ingresos_mensuales_cop", 0) <= 0:
        return "INFORMACION_INSUFICIENTE"
    if not (settings.monto_minimo_cop <= monto <= settings.monto_maximo_cop):
        return "MONTO_FUERA_DE_RANGO"
    if probabilidad >= umbral:
        return "RIESGO_ALTO"
    return None
