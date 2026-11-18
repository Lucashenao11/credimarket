import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';

import { AuthService } from '../../core/auth.service';
import { mensajeDeError } from '../../core/errores';
import { AvisoComponent } from '../../shared/aviso.component';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [ReactiveFormsModule, AvisoComponent],
  template: `
    <section class="tarjeta estrecha login">
      <h1>Iniciar sesión</h1>
      <app-aviso [texto]="auth.aviso()" tipo="info" />
      <form [formGroup]="form" (ngSubmit)="entrar()">
        <label>Usuario <input formControlName="usuario" autocomplete="username" /></label>
        @if (form.controls.usuario.touched && form.controls.usuario.invalid) { <small class="err">Escribe tu usuario.</small> }
        <label>Contraseña <input type="password" formControlName="password" autocomplete="current-password" /></label>
        @if (form.controls.password.touched && form.controls.password.invalid) { <small class="err">Escribe tu contraseña.</small> }
        <app-aviso [texto]="error()" />
        <button type="submit" [disabled]="enviando()">{{ enviando() ? 'Entrando…' : 'Entrar' }}</button>
      </form>
      <p class="nota">Cuentas de demostración: <b>admin</b>, <b>ana</b> y <b>beto</b>. Las contraseñas están en tu archivo <code>.env</code>
        (<code>DEMO_ADMIN_PASSWORD</code> y <code>DEMO_CLIENTE_PASSWORD</code>).</p>
    </section>
  `,
})
export class LoginComponent {
  auth = inject(AuthService);
  private router = inject(Router);
  private ruta = inject(ActivatedRoute);
  form = inject(FormBuilder).nonNullable.group({ usuario: ['', Validators.required], password: ['', Validators.required] });
  enviando = signal(false);
  error = signal<string | null>(null);

  entrar() {
    this.form.markAllAsTouched();
    if (this.form.invalid || this.enviando()) return;
    this.enviando.set(true);
    this.error.set(null);
    const { usuario, password } = this.form.getRawValue();
    this.auth.login(usuario, password).subscribe({
      next: () => {
        this.enviando.set(false);
        this.router.navigateByUrl(this.ruta.snapshot.queryParamMap.get('volver') || '/');
      },
      error: (e) => { this.enviando.set(false); this.error.set(mensajeDeError(e)); },
    });
  }
}
