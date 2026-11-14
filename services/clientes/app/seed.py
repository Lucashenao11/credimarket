"""Cuentas y clientes de demostración. Solo se crean con DEMO_TOKENS_ENABLED=true."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import Cliente, Usuario
from .security import hash_password

CLIENTES_DEMO = [
    # Perfil de bajo riesgo
    dict(cliente_id="CLI-DEMO-0001", nombre="Ana Demo", email="ana@demo.local",
         ingresos_mensuales_cop=6_000_000, obligaciones_mensuales_cop=500_000,
         tipo_empleo="dependiente", antiguedad_laboral_meses=60, meses_historial_crediticio=96,
         creditos_previos=3, atrasos_previos_30d=0, porcentaje_pago_puntual=98),
    # Perfil de alto riesgo
    dict(cliente_id="CLI-DEMO-0002", nombre="Beto Demo", email="beto@demo.local",
         ingresos_mensuales_cop=1_400_000, obligaciones_mensuales_cop=900_000,
         tipo_empleo="temporal", antiguedad_laboral_meses=2, meses_historial_crediticio=6,
         creditos_previos=4, atrasos_previos_30d=6, porcentaje_pago_puntual=55),
]


def sembrar_demo(db: Session) -> None:
    if not settings.demo_tokens_enabled:
        return
    for datos in CLIENTES_DEMO:
        if db.scalar(select(Cliente).where(Cliente.cliente_id == datos["cliente_id"])) is None:
            db.add(Cliente(**datos))
    cuentas = []
    if settings.demo_admin_password:
        cuentas.append(("admin", settings.demo_admin_password, "admin", None))
    if settings.demo_cliente_password:
        cuentas.append(("ana", settings.demo_cliente_password, "cliente", "CLI-DEMO-0001"))
        cuentas.append(("beto", settings.demo_cliente_password, "cliente", "CLI-DEMO-0002"))
    for usuario, password, rol, cliente_id in cuentas:
        if db.scalar(select(Usuario).where(Usuario.usuario == usuario)) is None:
            db.add(Usuario(usuario=usuario, password_hash=hash_password(password),
                           rol=rol, cliente_id=cliente_id))
    db.commit()
