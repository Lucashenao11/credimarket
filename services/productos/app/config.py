from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str
    database_url: str
    cors_origins: str = "http://localhost:4200"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
