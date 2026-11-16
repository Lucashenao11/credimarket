import { Component, OnDestroy, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { mensajeDeError } from '../../core/errores';
import { Historial, Prestamo } from '../../core/models';
import { AvisoComponent } from '../../shared/aviso.component';
import { EstadoBadgeComponent } from '../../shared/estado-badge.component';
import { CopPipe, EXPLICACION_ESTADO, FechaPipe, MOTIVOS } from '../../shared/formato';

@Component({
  selector: 'app-mis-prestamos',
  standalone: true,
  imports: [AvisoComponent, EstadoBadgeComponent, CopPipe, FechaPipe, RouterLink],
  template: `
    <h1>Mis solicitudes</h1>
    <app-aviso [texto]="error()" (reintentar)="cargar()" />
    <app-aviso [texto]="exito()" tipo="ok" />
    @if (hayPendientes()) { <p class="nota">Hay solicitudes en proceso: esta lista se actualiza sola cada 3 segundos.</p> }
    @if (cargando() && !lista().length) { <p>Cargando…</p> }
    @if (!cargando() && !error() && !lista().length) {
      <p class="vacio">Aún no tienes solicitudes. <a routerLink="/solicitar">Haz la primera</a>.</p>
    }
    <div class="lista">
      @for (p of lista(); track p.id) {
        <article class="tarjeta">
          <header class="fila">
            <app-estado [estado]="p.estado" />
            <small>{{ p.creado_en | fecha }}</small>
          </header>
          <p>{{ p.cantidad }} × producto #{{ p.producto_id }} · {{ p.plazo_meses }} meses · monto <b>{{ p.monto_cop | cop }}</b> · cuota <b>{{ p.cuota_cop | cop }}</b></p>
          <p class="nota">{{ explicacion(p.estado) }}@if (p.motivo) { <br>Motivo: {{ motivo(p.motivo) }}. }</p>
          <small class="nota">Precio y versión de cotización usados: {{ p.precio_unitario_cop | cop }} (v{{ p.version_cotizacion }}). Id: <code>{{ p.id }}</code></small>
          <div class="acciones">
            <button type="button" class="link" (click)="alternar(p.id)">{{ abierto() === p.id ? 'Ocultar historial' : 'Ver historial' }}</button>
            @if (puedeCancelar(p.estado)) {
              <button type="button" class="peligro" [disabled]="trabajando() === p.id" (click)="cancelar(p)">
                {{ trabajando() === p.id ? 'Cancelando…' : 'Cancelar solicitud' }}
              </button>
            }
          </div>
          @if (abierto() === p.id) {
            <ol class="historial">
              @for (h of historial(); track $index) {
                <li><b>{{ h.estado_nuevo.replaceAll('_', ' ') }}</b> · {{ h.en | fecha }}@if (h.motivo) { · {{ motivo(h.motivo) }} }</li>
              } @empty { <li>Cargando historial…</li> }
            </ol>
          }
        </article>
      }
    </div>
  `,
})
export class MisPrestamosComponent implements OnDestroy {
  private api = inject(ApiService);
  lista = signal<Prestamo[]>([]);
  cargando = signal(false);
  error = signal<string | null>(null);
  exito = signal<string | null>(null);
  abierto = signal<string | null>(null);
  historial = signal<Historial[]>([]);
  trabajando = signal<string | null>(null);
  hayPendientes = computed(() => this.lista().some((p) => p.estado === 'PENDIENTE_INVENTARIO'));
  private temporizador: ReturnType<typeof setInterval>;

  constructor() {
    inject(ActivatedRoute); // reservado para resaltar ?id=
    this.cargar();
    this.temporizador = setInterval(() => { if (this.hayPendientes()) this.cargar(true); }, 3000);
  }
  ngOnDestroy() { clearInterval(this.temporizador); }

  explicacion(e: string) { return EXPLICACION_ESTADO[e] ?? ''; }
  motivo(m: string) { return MOTIVOS[m] ?? m; }
  puedeCancelar(e: string) { return e === 'PENDIENTE_INVENTARIO' || e === 'APROBADA'; }

  cargar(silencioso = false) {
    if (!silencioso) { this.cargando.set(true); this.error.set(null); }
    this.api.prestamos().subscribe({
      next: (l) => { this.lista.set(l); this.cargando.set(false); if (silencioso) this.error.set(null); },
      error: (e) => { this.error.set(mensajeDeError(e)); this.cargando.set(false); },
    });
  }

  alternar(id: string) {
    if (this.abierto() === id) { this.abierto.set(null); return; }
    this.abierto.set(id);
    this.historial.set([]);
    this.api.historial(id).subscribe({ next: (h) => this.historial.set(h), error: (e) => this.error.set(mensajeDeError(e)) });
  }

  cancelar(p: Prestamo) {
    if (this.trabajando()) return;
    this.trabajando.set(p.id);
    this.error.set(null);
    this.api.cancelar(p.id).subscribe({
      next: () => { this.trabajando.set(null); this.exito.set('Solicitud cancelada.'); this.cargar(true); },
      error: (e) => { this.trabajando.set(null); this.error.set(mensajeDeError(e)); this.cargar(true); },
    });
  }
}
