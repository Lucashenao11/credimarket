import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { mensajeDeError } from '../../core/errores';
import { Cliente } from '../../core/models';
import { AvisoComponent } from '../../shared/aviso.component';

@Component({
  selector: 'app-perfil',
  standalone: true,
  imports: [ReactiveFormsModule, AvisoComponent],
  template: `
    <h1>Mi perfil</h1>
    <app-aviso [texto]="error()" (reintentar)="cargar()" />
    <app-aviso [texto]="exito()" tipo="ok" />
    @if (cliente(); as c) {
      <form class="tarjeta estrecha" [formGroup]="form" (ngSubmit)="guardar()">
        <p class="nota">Identificador: <code>{{ c.cliente_id }}</code></p>
        <label>Nombre <input formControlName="nombre" /></label>
        @if (form.controls.nombre.invalid && form.controls.nombre.touched) { <small class="err">El nombre es obligatorio.</small> }
        <label>Correo <input type="email" formControlName="email" /></label>
        @if (form.controls.email.invalid && form.controls.email.touched) { <small class="err">Escribe un correo válido.</small> }
        <button type="submit" [disabled]="guardando()">{{ guardando() ? 'Guardando…' : 'Guardar cambios' }}</button>
      </form>
    } @else if (!error()) { <p>Cargando…</p> }
  `,
})
export class PerfilComponent {
  private api = inject(ApiService);
  private auth = inject(AuthService);
  cliente = signal<Cliente | null>(null);
  error = signal<string | null>(null);
  exito = signal<string | null>(null);
  guardando = signal(false);
  form = inject(FormBuilder).nonNullable.group({ nombre: ['', Validators.required], email: ['', [Validators.required, Validators.email]] });

  constructor() { this.cargar(); }

  cargar() {
    const id = this.auth.sesion()?.clienteId;
    if (!id) { this.error.set('Tu sesión no tiene un cliente asociado.'); return; }
    this.error.set(null);
    this.api.cliente(id).subscribe({
      next: (c) => { this.cliente.set(c); this.form.patchValue({ nombre: c.nombre ?? '', email: c.email ?? '' }); },
      error: (e) => this.error.set(mensajeDeError(e)),
    });
  }

  guardar() {
    this.form.markAllAsTouched();
    const c = this.cliente();
    if (this.form.invalid || !c || this.guardando()) return;
    this.guardando.set(true);
    this.error.set(null);
    this.exito.set(null);
    this.api.actualizarCliente(c.cliente_id, this.form.getRawValue()).subscribe({
      next: (n) => { this.cliente.set(n); this.guardando.set(false); this.exito.set('Datos actualizados.'); },
      error: (e) => { this.guardando.set(false); this.error.set(mensajeDeError(e)); },
    });
  }
}
