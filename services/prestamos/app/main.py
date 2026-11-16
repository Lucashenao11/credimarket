import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .db import Base, db_disponible, engine
from . import consumidor, mensajeria, timeouts
from .riesgo import ModeloRiesgo
from .routers import modelo, prestamos

log = logging.getLogger("prestamos")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    app.state.modelo = None
    try:
        app.state.modelo = ModeloRiesgo(settings.model_registry_dir)
        log.info("Modelo cargado: %s", app.state.modelo.version)
    except Exception:
        # El servicio arranca igual; /ready dirá que no está listo y las solicitudes darán 503
        log.exception("No se pudo cargar el modelo desde %s", settings.model_registry_dir)
    detener = threading.Event()
    if settings.rabbitmq_url:  # sin URL (pruebas automáticas) no se arrancan los hilos
        mensajeria.Publicador(settings.rabbitmq_url, detener).start()
        mensajeria.Consumidor(settings.rabbitmq_url, mensajeria.COLA_PRESTAMOS,
                              consumidor.manejar_evento, detener).start()
        timeouts.iniciar(detener)
    yield
    detener.set()


app = FastAPI(title="CrediMarket - prestamos", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins_list,
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["Idempotent-Replay"])
app.include_router(prestamos.router)
app.include_router(modelo.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.service_name,
            "database": "ok" if db_disponible() else "no disponible"}


@app.get("/ready")
def ready(request: Request):
    base = db_disponible()
    mod = getattr(request.app.state, "modelo", None) is not None
    listo = base and mod
    return JSONResponse({"ready": listo, "database": base, "modelo": mod},
                        status_code=200 if listo else 503)
