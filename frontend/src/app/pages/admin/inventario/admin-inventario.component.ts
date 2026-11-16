import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { forkJoin } from 'rxjs';

import { ApiService } from '../../../core/api.service';
import { mensajeDeError } from '../../../core/errores';
import { Existencia, Movimiento, Reserva } from '../../../core/models';
import { AvisoComponent } from '../../../shared/aviso.component';
import { FechaPipe } from '../../../shared/formato';

@Component({
  selector: 'app-admin-inventario',
  standalone: true,
  imports: [ReactiveFormsModule, AvisoComponent, FechaPipe],
  template: `
    <h1>Inventario</h1>
    <app-aviso [texto]="error()" (reintentar)="cargar()" />
    <app-aviso [texto]="exito()" tipo="ok" />

    <h2>Existencias</h2>
    <div class="tabla-caja"><table>
      <thead><tr><th>Producto</th><th>Disponible</th><th>Reservado</th><th>Actualizado</th></tr></thead>
      <tbody>
        @for (e of existencias(); track e.producto_id) {
          <tr><td>#{{ e.producto_id }}</td><td>{{ e.disponible }}</td><td>{{ e.reservado }}</td><td>{{ e.actualizado_en | fecha }}</td></tr>
        } @empty { <tr><td colspan="4" class="vacio">{{ cargando() ? 'Cargando…' : 'Sin existencias registradas.' }}</td></tr> }
      </tbody>
    </table></div>

    <h2>Registrar entrada</h2>
    <form class="tarjeta fila" [formGroup]="form" (ngSubmit)="entrada()">
      <label>Producto <input type="number" formControlName="producto_id" min="1" /></label>
      <label>Cantidad <input type="number" formControlName="cantidad" min="1" /></label>
      <button type="submit" [disabled]="guardando()">{{ guardando() ? 'Registrando…' : 'Registrar' }}</button>
    </form>
    @if (form.touched && form.invalid) { <small class="err">Indica un producto y una cantidad enteros mayores que cero.</small> }

    <h2>Reservas</h2>
    <div class="tabla-caja"><table>
      <thead><tr><th>Préstamo</th><th>Producto</th><th>Cant.</th><th>Estado</th><th>Vence</th></tr></thead>
      <tbody>
        @for (r of reservas(); track r.prestamo_id) {
          <tr><td><code>{{ r.prestamo_id.slice(0, 8) }}</code></td><td>#{{ r.producto_id }}</td><td>{{ r.cantidad }}</td><td>{{ r.estado }}</td><td>{{ r.vence_en | fecha }}</td></tr>
        } @empty { <tr><td colspan="5" class="vacio">Sin reservas.</td></tr> }
      </tbody>
    </table></div>
    <p class="nota">Entregar y cancelar se hacen desde la pantalla Préstamos, porque el ciclo de vida lo gobierna el servicio de Préstamos.</p>

    <h2>Últimos movimientos</h2>
    <div class="tabla-caja"><table>
      <thead><tr><th>Fecha</th><th>Producto</th><th>Tipo</th><th>Cant.</th><th>Préstamo</th></tr></thead>
      <tbody>
        @for (m of movimientos(); track $index) {
          <tr><td>{{ m.creado_en | fecha }}</td><td>#{{ m.producto_id }}</td><td>{{ m.tipo }}</td><td>{{ m.cantidad }}</td><td><code>{{ m.prestamo_id ? m.prestamo_id.slice(0, 8) : '' }}</code></td></tr>
        } @empty { <tr><td colspan="5" class="vacio">Sin movimientos.</td></tr> }
      </tbody>
    </table></div>
  `,
})
export class AdminInventarioComponent {
  private api = inject(ApiService);
  existencias = signal<Existencia[]>([]);
  reservas = signal<Reserva[]>([]);
  movimientos = signal<Movimiento[]>([]);
  cargando = signal(false);
  guardando = signal(false);
  error = signal<string | null>(null);
  exito = signal<string | null>(null);
  form = inject(FormBuilder).group({
    producto_id: [null as number | null, [Validators.required, Validators.min(1)]],
    cantidad: [null as number | null, [Validators.required, Validators.min(1), Validators.pattern(/^\d+$/)]],
  });

  constructor() { this.cargar(); }

  cargar() {
    this.cargando.set(true);
    this.error.set(null);
    forkJoin({ e: this.api.existencias(), r: this.api.reservas(null), m: this.api.movimientos(null, 30) }).subscribe({
      next: ({ e, r, m }) => { this.existencias.set(e); this.reservas.set(r); this.movimientos.set(m); this.cargando.set(false); },
      error: (err) => { this.error.set(mensajeDeError(err)); this.cargando.set(false); },
    });
  }

  entrada() {
    this.form.markAllAsTouched();
    if (this.form.invalid || this.guardando()) return;
    const v = this.form.getRawValue();
    this.guardando.set(true);
    this.error.set(null);
    this.exito.set(null);
    this.api.registrarEntrada(Number(v.producto_id), Number(v.cantidad)).subscribe({
      next: () => { this.guardando.set(false); this.exito.set('Entrada registrada.'); this.form.reset(); this.cargar(); },
      error: (e) => { this.guardando.set(false); this.error.set(mensajeDeError(e)); },
    });
  }
}
