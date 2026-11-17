import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .cache import CacheProductos
from .config import settings
from .db import Base, SessionLocal, db_disponible, engine
from .routers import productos
from .seed import sembrar_demo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    app.state.cache = CacheProductos.desde_url(settings.redis_url, settings.cache_ttl_segundos,
                                               settings.redis_timeout_segundos,
                                               settings.redis_pausa_tras_fallo_segundos)
    with SessionLocal() as db:
        sembrar_demo(db)
    yield


app = FastAPI(title="CrediMarket - productos", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins_list,
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
                   # Sin esto el navegador oculta X-Cache al frontend (CORS solo expone cabeceras simples)
                   expose_headers=["X-Cache"])
app.include_router(productos.router)


@app.get("/health")
def health(request: Request):
    cache = getattr(request.app.state, "cache", None)
    return {"status": "ok", "service": settings.service_name,
            "database": "ok" if db_disponible() else "no disponible",
            # Informativo: Productos sigue respondiendo aunque Redis esté caído
            "redis": "ok" if cache is not None and cache.ping() else "no disponible"}
