from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "inventario"
    database_url: str
    cors_origins: str = "http://localhost:4200"

    # Solo la llave PÚBLICA: Inventario verifica tokens, nunca los emite (decisión D5)
    jwt_public_key_path: str = "/run/secrets/jwt_public.pem"
    jwt_issuer: str = "credimarket-clientes"
    jwt_audience: str = "credimarket"

    # Decisión D6: 30 minutos por defecto; 60 segundos en la demostración
    reserva_ttl_segundos: int = 1800
    vencimiento_intervalo_segundos: int = 10  # cada cuánto se revisan las reservas vencidas

    demo_datos: bool = False  # siembra existencias de ejemplo

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
