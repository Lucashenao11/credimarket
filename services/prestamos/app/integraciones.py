"""Llamadas HTTP a Clientes y Productos. Se reenvía el token del usuario (no hay tokens de servicio)."""
import httpx
from fastapi import HTTPException, status

from .config import settings


class Integraciones:
    def __init__(self, cliente_http: httpx.Client | None = None):
        self._http = cliente_http or httpx.Client(timeout=settings.http_timeout_segundos)

    def _get(self, url: str, token: str, recurso: str) -> dict:
        try:
            r = self._http.get(url, headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError:
            # Servicio caído o lento: no se decide nada con datos que no se pudieron obtener
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"No se pudo consultar {recurso}")
        if r.status_code == 404:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{recurso.capitalize()} no encontrado")
        if r.status_code != 200:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{recurso.capitalize()} respondió {r.status_code}")
        return r.json()

    def obtener_cliente(self, token: str, cliente_id: str) -> dict:
        return self._get(f"{settings.clientes_url}/clientes/{cliente_id}", token, "cliente")

    def obtener_cotizacion(self, token: str, producto_id: int) -> dict:
        return self._get(f"{settings.productos_url}/productos/{producto_id}/cotizacion", token, "producto")


_instancia: Integraciones | None = None


def get_integraciones() -> Integraciones:
    global _instancia
    if _instancia is None:
        _instancia = Integraciones()
    return _instancia
