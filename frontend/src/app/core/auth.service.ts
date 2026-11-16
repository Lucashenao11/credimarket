import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, tap } from 'rxjs';

import { ConfigService } from './config.service';
import { Rol } from './models';

export interface Sesion { token: string; usuario: string; rol: Rol; clienteId: string | null; exp: number; }

const CLAVE = 'credimarket.token';

function decodificar(token: string): Sesion | null {
  try {
    const p = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return { token, usuario: p.sub, rol: p.rol, clienteId: p.cliente_id ?? null, exp: p.exp };
  } catch {
    return null;
  }
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);
  private cfg = inject(ConfigService);
  private router = inject(Router);

  private _sesion = signal<Sesion | null>(this.leer());
  readonly sesion = this._sesion.asReadonly();
  readonly esAdmin = computed(() => this._sesion()?.rol === 'admin');
  readonly esCliente = computed(() => this._sesion()?.rol === 'cliente');
  /** Mensaje para mostrar en el login (p. ej. "tu sesión venció"). */
  readonly aviso = signal<string | null>(null);

  private leer(): Sesion | null {
    try {
      const t = sessionStorage.getItem(CLAVE);
      const s = t ? decodificar(t) : null;
      return s && s.exp * 1000 > Date.now() ? s : null;
    } catch {
      return null; // el almacenamiento puede estar bloqueado: la app funciona sin recordar la sesión
    }
  }

  vigente(): boolean {
    const s = this._sesion();
    return !!s && s.exp * 1000 > Date.now();
  }

  login(usuario: string, password: string): Observable<unknown> {
    return this.http.post<{ access_token: string }>(`${this.cfg.cfg.clientes}/auth/login`, { usuario, password }).pipe(
      tap((r) => {
        const s = decodificar(r.access_token);
        if (!s) throw new Error('Token ilegible');
        try { sessionStorage.setItem(CLAVE, r.access_token); } catch { /* sin almacenamiento */ }
        this.aviso.set(null);
        this._sesion.set(s);
      }),
    );
  }

  logout(aviso: string | null = null): void {
    try { sessionStorage.removeItem(CLAVE); } catch { /* sin almacenamiento */ }
    this._sesion.set(null);
    this.aviso.set(aviso);
    this.router.navigate(['/login']);
  }
}
