import { HttpClient, HttpParams, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ConfigService } from './config.service';
import {
  Cliente, Existencia, Historial, Producto, ProductoIn, ModeloInfo, Movimiento, Prestamo, ReporteImportacion, Reserva, SolicitudIn,
} from './models';

/** Todas las llamadas a los cuatro servicios, en un solo lugar. */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private cfg = inject(ConfigService);
  private get u() { return this.cfg.cfg; }

  // ---- Productos
  productos(soloActivos = true): Observable<Producto[]> {
    return this.http.get<Producto[]>(`${this.u.productos}/productos`, { params: new HttpParams().set('solo_activos', soloActivos) });
  }
  /** Respuesta completa: la cabecera X-Cache (HIT/MISS) dice si el dato vino de Redis. */
  producto(id: number): Observable<HttpResponse<Producto>> {
    return this.http.get<Producto>(`${this.u.productos}/productos/${id}`, { observe: 'response' });
  }
  crearProducto(p: ProductoIn) { return this.http.post<Producto>(`${this.u.productos}/productos`, p); }
  /** Solo se envían los campos que cambian; el servidor sube la versión. */
  actualizarProducto(id: number, cambios: Partial<ProductoIn>) {
    return this.http.put<Producto>(`${this.u.productos}/productos/${id}`, cambios);
  }
  /** Borrado lógico: activo = false y la versión sube. */
  desactivarProducto(id: number) { return this.http.delete<Producto>(`${this.u.productos}/productos/${id}`); }

  // ---- Clientes
  cliente(id: string) { return this.http.get<Cliente>(`${this.u.clientes}/clientes/${id}`); }
  clientes(limit: number, offset: number) {
    return this.http.get<Cliente[]>(`${this.u.clientes}/clientes`, { params: new HttpParams().set('limit', limit).set('offset', offset) });
  }
  crearCliente(c: Partial<Cliente>) { return this.http.post<Cliente>(`${this.u.clientes}/clientes`, c); }
  actualizarCliente(id: string, cambios: Partial<Cliente>) { return this.http.patch<Cliente>(`${this.u.clientes}/clientes/${id}`, cambios); }
  importarClientes(archivo: File): Observable<ReporteImportacion> {
    const f = new FormData();
    f.append('archivo', archivo);
    return this.http.post<ReporteImportacion>(`${this.u.clientes}/clientes/importar`, f);
  }

  // ---- Préstamos
  solicitar(s: SolicitudIn, clave: string): Observable<HttpResponse<Prestamo>> {
    return this.http.post<Prestamo>(`${this.u.prestamos}/prestamos`, s, { headers: { 'Idempotency-Key': clave }, observe: 'response' });
  }
  prestamos(limit = 100) { return this.http.get<Prestamo[]>(`${this.u.prestamos}/prestamos`, { params: new HttpParams().set('limit', limit) }); }
  historial(id: string) { return this.http.get<Historial[]>(`${this.u.prestamos}/prestamos/${id}/historial`); }
  cancelar(id: string) { return this.http.post<Prestamo>(`${this.u.prestamos}/prestamos/${id}/cancelar`, {}); }
  entregar(id: string) { return this.http.post<{ resultado: string }>(`${this.u.prestamos}/prestamos/${id}/entregar`, {}); }
  modeloInfo() { return this.http.get<ModeloInfo>(`${this.u.prestamos}/modelo/info`); }

  // ---- Inventario (solo administrador)
  existencias() { return this.http.get<Existencia[]>(`${this.u.inventario}/existencias`); }
  registrarEntrada(productoId: number, cantidad: number) {
    return this.http.post<Existencia>(`${this.u.inventario}/existencias/${productoId}/entradas`, { cantidad });
  }
  reservas(estado: string | null, limit = 100) {
    let p = new HttpParams().set('limit', limit);
    if (estado) p = p.set('estado', estado);
    return this.http.get<Reserva[]>(`${this.u.inventario}/reservas`, { params: p });
  }
  movimientos(productoId: number | null, limit = 100) {
    let p = new HttpParams().set('limit', limit);
    if (productoId) p = p.set('producto_id', productoId);
    return this.http.get<Movimiento[]>(`${this.u.inventario}/movimientos`, { params: p });
  }
}
