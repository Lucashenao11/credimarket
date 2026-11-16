import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiService } from '../../../core/api.service';
import { mensajeDeError } from '../../../core/errores';
import { Cliente, ReporteImportacion } from '../../../core/models';
import { AvisoComponent } from '../../../shared/aviso.component';

@Component({
  selector: 'app-admin-clientes',
  standalone: true,
  imports: [ReactiveFormsModule, AvisoComponent],
  template: `
    <h1>Clientes</h1>
    <app-aviso [texto]="error()" (reintentar)="cargar()" />
    <app-aviso [texto]="exito()" tipo="ok" />

    <div class="tabla-caja"><table>
      <thead><tr><th>Id</th><th>Nombre</th><th>Correo</th><th>Ingresos</th><th>Activo</th><th></th></tr></thead>
      <tbody>
        @for (c of lista(); track c.cliente_id) {
          <tr>
            <td><code>{{ c.cliente_id.slice(0, 8) }}</code></td><td>{{ c.nombre }}</td><td>{{ c.email }}</td>
            <td>{{ c.ingresos_mensuales_cop }}</td><td>{{ c.activo ? 'Sí' : 'No' }}</td>
            <td><button type="button" class="link" (click)="alternarActivo(c)">{{ c.activo ? 'Desactivar' : 'Activar' }}</button></td>
          </tr>
        } @empty { <tr><td colspan="6" class="vacio">{{ cargando() ? 'Cargando…' : 'No hay clientes.' }}</td></tr> }
      </tbody>
    </table></div>
    <div class="fila">
      <button type="button" class="link" [disabled]="offset() === 0" (click)="pagina(-1)">‹ Anterior</button>
      <small>Registros {{ offset() + 1 }}–{{ offset() + lista().length }}</small>
      <button type="button" class="link" [disabled]="lista().length < tam" (click)="pagina(1)">Siguiente ›</button>
    </div>

    <h2>Crear cliente</h2>
    <form class="tarjeta" [formGroup]="form" (ngSubmit)="crear()">
      <label>Nombre <input formControlName="nombre" /></label>
      <label>Correo <input type="email" formControlName="email" /></label>
      <label>Ingresos mensuales (COP) <input type="number" formControlName="ingresos_mensuales_cop" min="0" /></label>
      <label>Obligaciones mensuales (COP) <input type="number" formControlName="obligaciones_mensuales_cop" min="0" /></label>
      @if (form.touched && form.invalid) { <small class="err">Nombre, correo válido e importes mayores o iguales a cero son obligatorios.</small> }
      <button type="submit" [disabled]="guardando()">{{ guardando() ? 'Creando…' : 'Crear cliente' }}</button>
    </form>

    <h2>Importar CSV</h2>
    <div class="tarjeta">
      <input type="file" accept=".csv" (change)="elegir($event)" />
      <button type="button" [disabled]="!archivo || importando()" (click)="importar()">{{ importando() ? 'Importando…' : 'Importar' }}</button>
      @if (reporte(); as r) {
        <p><b>{{ r.archivo }}</b>: {{ r.total_filas }} filas · {{ r.insertados }} insertadas · {{ r.ya_existian }} ya existían · {{ r.errores }} con error</p>
        @if (r.errores) {
          <ul>@for (f of r.filas; track f.fila) { @if (f.resultado === 'error') { <li>Fila {{ f.fila }}: {{ f.detalle }}</li> } }</ul>
        }
      }
    </div>
  `,
})
export class AdminClientesComponent {
  private api = inject(ApiService);
  readonly tam = 20;
  lista = signal<Cliente[]>([]);
  offset = signal(0);
  cargando = signal(false);
  guardando = signal(false);
  importando = signal(false);
  error = signal<string | null>(null);
  exito = signal<string | null>(null);
  reporte = signal<ReporteImportacion | null>(null);
  archivo: File | null = null;
  form = inject(FormBuilder).group({
    nombre: ['', Validators.required],
    email: ['', [Validators.required, Validators.email]],
    ingresos_mensuales_cop: [0, [Validators.required, Validators.min(0)]],
    obligaciones_mensuales_cop: [0, [Validators.required, Validators.min(0)]],
  });

  constructor() { this.cargar(); }

  cargar() {
    this.cargando.set(true);
    this.error.set(null);
    this.api.clientes(this.tam, this.offset()).subscribe({
      next: (l) => { this.lista.set(l); this.cargando.set(false); },
      error: (e) => { this.error.set(mensajeDeError(e)); this.cargando.set(false); },
    });
  }
  pagina(d: number) { this.offset.update((o) => Math.max(0, o + d * this.tam)); this.cargar(); }

  crear() {
    this.form.markAllAsTouched();
    if (this.form.invalid || this.guardando()) return;
    this.guardando.set(true);
    this.error.set(null);
    this.exito.set(null);
    this.api.crearCliente(this.form.getRawValue() as Partial<Cliente>).subscribe({
      next: () => { this.guardando.set(false); this.exito.set('Cliente creado.'); this.form.reset({ nombre: '', email: '', ingresos_mensuales_cop: 0, obligaciones_mensuales_cop: 0 }); this.cargar(); },
      error: (e) => { this.guardando.set(false); this.error.set(mensajeDeError(e)); },
    });
  }

  alternarActivo(c: Cliente) {
    this.error.set(null);
    this.api.actualizarCliente(c.cliente_id, { activo: !c.activo }).subscribe({
      next: () => this.cargar(),
      error: (e) => this.error.set(mensajeDeError(e)),
    });
  }

  elegir(ev: Event) { this.archivo = (ev.target as HTMLInputElement).files?.[0] ?? null; }

  importar() {
    if (!this.archivo || this.importando()) return;
    this.importando.set(true);
    this.error.set(null);
    this.reporte.set(null);
    this.api.importarClientes(this.archivo).subscribe({
      next: (r) => { this.importando.set(false); this.reporte.set(r); this.cargar(); },
      error: (e) => { this.importando.set(false); this.error.set(mensajeDeError(e)); },
    });
  }
}
