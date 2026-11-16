import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { mensajeDeError } from '../../core/errores';
import { Producto } from '../../core/models';
import { AvisoComponent } from '../../shared/aviso.component';
import { CopPipe } from '../../shared/formato';

/**
 * Catálogo — VERSIÓN BÁSICA (solo lectura).
 * TODO(Juan David): detalle de producto; vista de administrador para crear, actualizar y desactivar
 * (POST /productos, PUT /productos/{id}, DELETE /productos/{id}); mostrar la versión del producto.
 */
@Component({
  selector: 'app-catalogo',
  standalone: true,
  imports: [AvisoComponent, CopPipe, RouterLink],
  template: `
    <h1>Catálogo</h1>
    <app-aviso [texto]="error()" (reintentar)="cargar()" />
    @if (cargando()) { <p>Cargando…</p> }
    <div class="rejilla">
      @for (p of productos(); track p.id) {
        <article class="tarjeta">
          <small>{{ p.categoria }}</small>
          <h3>{{ p.nombre }}</h3>
          <p class="precio">{{ p.precio_cop | cop }}</p>
          @if (auth.esCliente()) { <a class="boton" [routerLink]="['/solicitar']" [queryParams]="{ producto: p.id }">Solicitar a crédito</a> }
        </article>
      } @empty {
        @if (!cargando() && !error()) { <p>No hay productos activos.</p> }
      }
    </div>
  `,
})
export class CatalogoComponent {
  private api = inject(ApiService);
  auth = inject(AuthService);
  productos = signal<Producto[]>([]);
  cargando = signal(false);
  error = signal<string | null>(null);

  constructor() { this.cargar(); }

  cargar() {
    this.cargando.set(true);
    this.error.set(null);
    this.api.productos().subscribe({
      next: (p) => { this.productos.set(p); this.cargando.set(false); },
      error: (e) => { this.error.set(mensajeDeError(e)); this.cargando.set(false); },
    });
  }
}
