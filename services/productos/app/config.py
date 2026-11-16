from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "productos"
    database_url: str
    cors_origins: str = "http://localhost:4200"

    jwt_public_key_path: str = "/run/secrets/jwt_public.pem"
    jwt_issuer: str = "credimarket-clientes"
    jwt_audience: str = "credimarket"

    demo_datos: bool = False  # siembra productos de ejemplo

    # TODO(compañero): Redis (REDIS_URL ya llega por docker-compose). Ver docs/guias/productos.md
    # redis_url: str = ""
    # cache_ttl_segundos: int = 300

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
