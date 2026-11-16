from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"protected_namespaces": ()}  # permite el campo model_registry_dir

    service_name: str = "prestamos"
    database_url: str
    cors_origins: str = "http://localhost:4200"

    jwt_public_key_path: str = "/run/secrets/jwt_public.pem"
    jwt_issuer: str = "credimarket-clientes"
    jwt_audience: str = "credimarket"

    rabbitmq_url: str = ""  # vacío = sin broker (pruebas automáticas)

    clientes_url: str = "http://clientes:8000"
    productos_url: str = "http://productos:8000"
    http_timeout_segundos: float = 3.0

    model_registry_dir: str = "/models"

    # Reglas de negocio (rango visto en el entrenamiento: 0.5 a 15 millones)
    monto_minimo_cop: int = 500_000
    monto_maximo_cop: int = 15_000_000
    tasa_mensual: float = 0.018

    # Decisión D6
    timeout_inventario_segundos: int = 60

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
