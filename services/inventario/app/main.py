import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import consumidor, mensajeria, vencimiento
from .config import settings
from .db import Base, SessionLocal, db_disponible, engine
from .routers import inventario
from .seed import sembrar_demo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        sembrar_demo(db)
    detener = vencimiento.iniciar()
    if settings.rabbitmq_url:  # sin URL (pruebas automáticas) no se arrancan los hilos
        mensajeria.Publicador(settings.rabbitmq_url, detener).start()
        mensajeria.Consumidor(settings.rabbitmq_url, mensajeria.COLA_INVENTARIO,
                              consumidor.manejar_comando, detener).start()
    yield
    detener.set()


app = FastAPI(title="CrediMarket - inventario", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(inventario.router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": settings.service_name,
        "database": "ok" if db_disponible() else "no disponible",
    }
