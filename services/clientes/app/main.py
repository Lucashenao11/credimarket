from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import Base, SessionLocal, db_disponible, engine
from .routers import auth, clientes
from .seed import sembrar_demo


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)  # crea las tablas si no existen
    with SessionLocal() as db:
        sembrar_demo(db)
    yield


app = FastAPI(title="CrediMarket - clientes", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(clientes.router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": settings.service_name,
        "database": "ok" if db_disponible() else "no disponible",
    }
