from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "clientes"
    database_url: str
    cors_origins: str = "http://localhost:4200"

    # JWT RS256: Clientes es el único servicio con la llave privada (decisión D5)
    jwt_private_key_path: str = "/run/secrets/jwt_private.pem"
    jwt_public_key_path: str = "/run/secrets/jwt_public.pem"
    jwt_issuer: str = "credimarket-clientes"
    jwt_audience: str = "credimarket"
    jwt_ttl_minutes: int = 60

    # Cuentas de demostración: solo existen si el modo demo está activo
    demo_tokens_enabled: bool = False
    demo_admin_password: str | None = None
    demo_cliente_password: str | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
