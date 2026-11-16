import { Injectable } from '@angular/core';

export interface AppConfig {
  clientes: string; productos: string; prestamos: string; inventario: string; mlflow: string; rabbitmq: string;
}

const POR_DEFECTO: AppConfig = {
  clientes: 'http://localhost:8002', productos: 'http://localhost:8001', prestamos: 'http://localhost:8003',
  inventario: 'http://localhost:8004', mlflow: 'http://localhost:5000', rabbitmq: 'http://localhost:15672',
};

@Injectable({ providedIn: 'root' })
export class ConfigService {
  cfg: AppConfig = POR_DEFECTO;

  async cargar(): Promise<void> {
    try {
      const r = await fetch('/config.json', { cache: 'no-store' });
      if (r.ok) this.cfg = { ...POR_DEFECTO, ...(await r.json()) };
    } catch {
      // sin config.json se usan los valores por defecto (puertos del docker-compose)
    }
  }

  /** ¿Esta URL pertenece a una de nuestras APIs? (el token solo se envía a ellas) */
  esApi(url: string): boolean {
    return [this.cfg.clientes, this.cfg.productos, this.cfg.prestamos, this.cfg.inventario].some((b) => url.startsWith(b));
  }
}
