import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { mensajeDeError } from '../../core/errores';
import { Producto } from '../../core/models';
import { AvisoComponent } from '../../shared/aviso.component';
import { CopPipe } from '../../shared/formato';

/** Tasa mensual con la que Préstamos calcula la cuota (contrato 4.3). Aquí solo sirve para una ESTIMACIÓN. */
const TASA_MENSUAL = 0.018;

/**
 * Detalle de un producto: GET /productos/{id}, que usa la caché Redis (la cabecera X-Cache se muestra).
 * El cliente elige cantidad y plazo y pasa a Solicitar con ambos ya elegidos.
 * Los importes son una estimación: el monto real lo calcula Préstamos con la cotización vigente.
 */
@Component({
  selector: 'app-producto-detalle',
  standalone: true,
  imports: [AvisoComponent, CopPipe, RouterLink, FormsModule],
  styles: [`
    .cabecera { display:flex; justify-content:space-between; align-items:baseline; gap:1rem; flex-wrap:wrap; }
    dl { display:grid; grid-template-columns:max-content 1fr; gap:.35rem 1.2rem; margin:.8rem 0; }
    dt { color:var(--suave); }
    dd { margin:0; font-variant-numeric:tabular-nums; }
    .cache { font-size:.78rem; padding:.1rem .5rem; border-radius:999px; background:var(--papel); color:var(--suave); }
    .simulador { display:flex; gap:1rem; flex-wrap:wrap; align-items:flex-end; }
    .simulador label { margin:.3rem 0; }
    .estimado { font:700 1.3rem var(--titulo); color:var(--petroleo); }
  `],
  template: `
    <p><a routerLink="/catalogo">‹ Volver al catálogo</a></p>
    <app-aviso [texto]="error()" (reintentar)="cargar()" />
    @if (cargando()) { <p>Cargando…</p> }

    @if (producto(); as p) {
      <section class="tarjeta">
        <div class="cabecera">
          <h1 style="margin:.2rem 0">{{ p.nombre }}</h1>
          @if (xCache()) {
            <span class="cache" title="Cabecera X-Cache de Productos">
              {{ xCache() === 'HIT' ? 'Servido desde la caché (Redis)' : 'Leído de la base de datos' }}</span>
          }
        </div>
        <p class="precio">{{ p.precio_cop | cop }}</p>
        <dl>
          <dt>Categoría</dt><dd>{{ p.categoria }}</dd>
          <dt>Referencia</dt><dd>#{{ p.id }}</dd>
          <dt>Versión</dt><dd>{{ p.version }} <small class="nota">(sube con cada cambio de precio, nombre, categoría o estado)</small></dd>
          <dt>Estado</dt><dd>{{ p.activo ? 'Disponible para solicitar' : 'Inactivo: no se puede solicitar' }}</dd>
        </dl>
      </section>

      @if (auth.esCliente() && p.activo) {
        <section class="tarjeta">
          <h2 style="margin-top:0">Financiación</h2>
          <div class="simulador">
            <label>Cantidad
              <input type="number" min="1" max="5" step="1" [ngModel]="cantidad()" (ngModelChange)="cantidad.set(+$event)" />
            </label>
            <label>Plazo
              <select [ngModel]="plazo()" (ngModelChange)="plazo.set(+$event)">
                @for (m of plazos; track m) { <option [ngValue]="m">{{ m }} meses</option> }
              </select>
            </label>
          </div>
          @if (cantidadValida()) {
            <p>Monto de lista: <b>{{ montoLista() | cop }}</b></p>
            <p>Cuota estimada: <span class="estimado">{{ cuotaEstimada() | cop }}</span> / mes durante {{ plazo() }} meses</p>
            <p class="nota">Estimación con tasa del 1,8 % mensual. El monto y la cuota definitivos los calcula el servidor
              con la cotización vigente al enviar la solicitud; la aprobación depende de la evaluación de riesgo y del inventario.</p>
            <a class="boton" [routerLink]="['/solicitar']" [queryParams]="{ producto: p.id, cantidad: cantidad(), plazo: plazo() }">
              Solicitar a crédito</a>
          } @else {
            <small class="err">La cantidad debe ser un entero entre 1 y 5.</small>
          }
        </section>
      }
    }
  `,
})
export class ProductoDetalleComponent {
  private api = inject(ApiService);
  private ruta = inject(ActivatedRoute);
  auth = inject(AuthService);
  readonly plazos = [6, 12, 18, 24, 36];

  producto = signal<Producto | null>(null);
  xCache = signal<string | null>(null);
  cargando = signal(false);
  error = signal<string | null>(null);
  cantidad = signal(1);
  plazo = signal(12);

  cantidadValida = computed(() => Number.isInteger(this.cantidad()) && this.cantidad() >= 1 && this.cantidad() <= 5);
  montoLista = computed(() => (this.producto()?.precio_cop ?? 0) * this.cantidad());
  /** cuota = monto · i / (1 − (1 + i)^−n), la misma fórmula de Préstamos */
  cuotaEstimada = computed(() => {
    const i = TASA_MENSUAL, n = this.plazo();
    return (this.montoLista() * i) / (1 - Math.pow(1 + i, -n));
  });

  constructor() { this.cargar(); }

  cargar() {
    const id = Number(this.ruta.snapshot.paramMap.get('id'));
    if (!Number.isInteger(id) || id < 1) { this.error.set('Producto no válido.'); return; }
    this.cargando.set(true);
    this.error.set(null);
    this.api.producto(id).subscribe({
      next: (r) => { this.producto.set(r.body); this.xCache.set(r.headers.get('X-Cache')); this.cargando.set(false); },
      error: (e) => { this.error.set(mensajeDeError(e)); this.cargando.set(false); },
    });
  }
}
