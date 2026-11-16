import { Component, inject, signal } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiService } from '../../../core/api.service';
import { mensajeDeError } from '../../../core/errores';
import { Prestamo } from '../../../core/models';
import { AvisoComponent } from '../../../shared/aviso.component';
import { EstadoBadgeComponent } from '../../../shared/estado-badge.component';
import { CopPipe, FechaPipe, MOTIVOS } from '../../../shared/formato';

@Component({
  selector: 'app-admin-prestamos',
  standalone: true,
  imports: [AvisoComponent, EstadoBadgeComponent, CopPipe, FechaPipe],
  template: `
    <h1>Préstamos</h1>
    <app-aviso [texto]="error()" (reintentar)="cargar()" />
    <app-aviso [texto]="exito()" tipo="ok" />
    <button type="button" (click)="cargar()" [disabled]="cargando()">{{ cargando() ? 'Actualizando…' : 'Actualizar' }}</button>
    <div class="tabla-caja">
    <table>
      <thead><tr><th>Creado</th><th>Cliente</th><th>Producto</th><th>Monto</th><th>Riesgo</th><th>Estado</th><th>Motivo</th><th></th></tr></thead>
      <tbody>
        @for (p of lista(); track p.id) {
          <tr>
            <td>{{ p.creado_en | fecha }}</td>
            <td><code>{{ p.cliente_id.slice(0, 8) }}</code></td>
            <td>{{ p.cantidad }} × #{{ p.producto_id }}</td>
            <td>{{ p.monto_cop | cop }}</td>
            <td>{{ p.probabilidad_incumplimiento == null ? '—' : (p.probabilidad_incumplimiento * 100).toFixed(1) + ' %' }}</td>
            <td><app-estado [estado]="p.estado" /></td>
            <td>{{ p.motivo ? (motivos[p.motivo] || p.motivo) : '' }}</td>
            <td class="acciones">
              @if (p.estado === 'APROBADA') {
                <button type="button" [disabled]="trabajando() === p.id" (click)="entregar(p)">Entregar</button>
              }
              @if (p.estado === 'APROBADA' || p.estado === 'PENDIENTE_INVENTARIO') {
                <button type="button" class="peligro" [disabled]="trabajando() === p.id" (click)="cancelar(p)">Cancelar</button>
              }
            </td>
          </tr>
        } @empty { <tr><td colspan="8" class="vacio">{{ cargando() ? 'Cargando…' : 'No hay préstamos.' }}</td></tr> }
      </tbody>
    </table>
    </div>
  `,
})
export class AdminPrestamosComponent {
  private api = inject(ApiService);
  motivos = MOTIVOS;
  lista = signal<Prestamo[]>([]);
  cargando = signal(false);
  error = signal<string | null>(null);
  exito = signal<string | null>(null);
  trabajando = signal<string | null>(null);

  constructor() { this.cargar(); }

  cargar() {
    this.cargando.set(true);
    this.error.set(null);
    this.api.prestamos(200).subscribe({
      next: (l) => { this.lista.set(l); this.cargando.set(false); },
      error: (e) => { this.error.set(mensajeDeError(e)); this.cargando.set(false); },
    });
  }

  private accion(p: Prestamo, f: () => Observable<unknown>, ok: string) {
    if (this.trabajando()) return;
    this.trabajando.set(p.id);
    this.error.set(null);
    this.exito.set(null);
    f().subscribe({
      next: () => { this.trabajando.set(null); this.exito.set(ok); this.cargar(); },
      error: (e) => { this.trabajando.set(null); this.error.set(mensajeDeError(e)); this.cargar(); },
    });
  }
  entregar(p: Prestamo) { this.accion(p, () => this.api.entregar(p.id), 'Entrega solicitada: Inventario confirmará la salida y el préstamo pasará a COMPLETADA.'); }
  cancelar(p: Prestamo) { this.accion(p, () => this.api.cancelar(p.id), 'Préstamo cancelado y reserva liberada.'); }
}
