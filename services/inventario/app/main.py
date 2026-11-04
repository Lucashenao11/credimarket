from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import db_disponible

app = FastAPI(title=f"CrediMarket - {settings.service_name}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    """El proceso responde. Informa, sin fallar, si la base de datos es alcanzable."""
    return {
        "status": "ok",
        "service": settings.service_name,
        "database": "ok" if db_disponible() else "no disponible",
    }
