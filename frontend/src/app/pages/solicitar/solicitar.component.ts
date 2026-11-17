import { Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { mensajeDeError, nuevoUuid } from '../../core/errores';
import { Prestamo, Producto } from '../../core/models';
import { AvisoComponent } from '../../shared/aviso.component';
import { EstadoBadgeComponent } from '../../shared/estado-badge.component';
import { CopPipe, EXPLICACION_ESTADO } from '../../shared/formato';

@Component({
  selector: 'app-solicitar',
  standalone: true,
  imports: [ReactiveFormsModule, AvisoComponent, EstadoBadgeComponent, CopPipe, RouterLink],
  template: `
    <h1>Solicitar financiación</h1>
    <app-aviso [texto]="errorCarga()" (reintentar)="cargarProductos()" />

    @if (confirmacion(); as p) {
      <section class="tarjeta ok-borde">
        <h2>Solicitud recibida</h2>
        <p>Identificador: <code>{{ p.id }}</code></p>
        <p>Estado: <app-estado [estado]="p.estado" /></p>
        <p>{{ explicacion(p.estado) }}</p>
        <p>Monto calculado con la cotización vigente: <b>{{ p.monto_cop | cop }}</b> · cuota estimada <b>{{ p.cuota_cop | cop }}</b> / mes</p>
        <a class="boton" routerLink="/mis-prestamos" [queryParams]="{ id: p.id }">Ver seguimiento</a>
        <button type="button" class="link" (click)="otra()">Hacer otra solicitud</button>
      </section>
    } @else {
      <form class="tarjeta estrecha" [formGroup]="form" (ngSubmit)="enviar()">
        <label>Producto
          <select formControlName="producto_id">
            <option [ngValue]="null" disabled>Elige un producto…</option>
            @for (p of productos(); track p.id) { <option [ngValue]="p.id">{{ p.nombre }} — {{ p.precio_cop | cop }}</option> }
          </select>
        </label>
        @if (tocado('producto_id')) { <small class="err">Elige un producto.</small> }
        <label>Cantidad
          <input type="number" formControlName="cantidad" min="1" max="5" />
        </label>
        @if (tocado('cantidad')) { <small class="err">La cantidad debe ser un entero entre 1 y 5.</small> }
        <label>Plazo
          <select formControlName="plazo_meses">
            @for (m of plazos; track m) { <option [ngValue]="m">{{ m }} meses</option> }
          </select>
        </label>
        @if (listado(); as l) { <p class="nota">Precio de lista: <b>{{ l | cop }}</b>. El monto final lo define la cotización vigente en el servidor, no este formulario.</p> }
        <app-aviso [texto]="errorEnvio()" (reintentar)="enviar()" />
        <button type="submit" [disabled]="enviando()">{{ enviando() ? 'Enviando…' : 'Enviar solicitud' }}</button>
        @if (claveVisible()) { <small class="nota">Clave de idempotencia de este intento: <code>{{ claveVisible() }}</code> (se conserva si reintentas).</small> }
      </form>
    }
  `,
})
export class SolicitarComponent {
  private api = inject(ApiService);
  private ruta = inject(ActivatedRoute);
  readonly plazos = [6, 12, 18, 24, 36];

  productos = signal<Producto[]>([]);
  errorCarga = signal<string | null>(null);
  errorEnvio = signal<string | null>(null);
  enviando = signal(false);
  confirmacion = signal<Prestamo | null>(null);
  claveVisible = signal<string | null>(null);

  form = inject(FormBuilder).group({
    producto_id: [null as number | null, Validators.required],
    cantidad: [1, [Validators.required, Validators.min(1), Validators.max(5), Validators.pattern(/^\d+$/)]],
    plazo_meses: [12, Validators.required],
  });
  private valor = signal(this.form.getRawValue());
  listado = computed(() => {
    const v = this.valor();
    const p = this.productos().find((x) => x.id === v.producto_id);
    return p && v.cantidad ? p.precio_cop * Number(v.cantidad) : null;
  });

  // Idempotency-Key: se crea UNA vez por intento y se reutiliza al reintentar con el mismo contenido.
  // Si la persona cambia el formulario, es otra solicitud y se genera otra clave.
  private clave: string | null = null;
  private huella = '';

  constructor() {
    this.form.valueChanges.subscribe(() => this.valor.set(this.form.getRawValue()));
    this.cargarProductos();
  }

  cargarProductos() {
    this.errorCarga.set(null);
    this.api.productos().subscribe({
      next: (p) => {
        this.productos.set(p);
        const q = this.ruta.snapshot.queryParamMap;
        const pre = Number(q.get('producto'));
        if (pre && p.some((x) => x.id === pre)) this.form.patchValue({ producto_id: pre });
        // Cantidad y plazo elegidos en el detalle del catálogo (solo si son válidos)
        const cantidad = Number(q.get('cantidad'));
        if (Number.isInteger(cantidad) && cantidad >= 1 && cantidad <= 5) this.form.patchValue({ cantidad });
        const plazo = Number(q.get('plazo'));
        if (this.plazos.includes(plazo)) this.form.patchValue({ plazo_meses: plazo });
      },
      error: (e) => this.errorCarga.set(mensajeDeError(e)),
    });
  }

  tocado(campo: 'producto_id' | 'cantidad') {
    const c = this.form.controls[campo];
    return c.invalid && (c.touched || c.dirty);
  }

  explicacion(estado: string) { return EXPLICACION_ESTADO[estado] ?? ''; }

  private obtenerClave(): string {
    const h = JSON.stringify(this.form.getRawValue());
    if (!this.clave || h !== this.huella) { this.clave = nuevoUuid(); this.huella = h; }
    return this.clave;
  }

  enviar() {
    this.form.markAllAsTouched();
    if (this.form.invalid || this.enviando()) return; // evita envíos duplicados mientras hay uno en curso
    const v = this.form.getRawValue();
    const clave = this.obtenerClave();
    this.claveVisible.set(clave);
    this.enviando.set(true);
    this.errorEnvio.set(null);
    this.api.solicitar({ producto_id: v.producto_id!, cantidad: Number(v.cantidad), plazo_meses: Number(v.plazo_meses) }, clave).subscribe({
      next: (r) => { this.enviando.set(false); this.confirmacion.set(r.body); this.clave = null; },
      error: (e) => { this.enviando.set(false); this.errorEnvio.set(mensajeDeError(e)); }, // la clave se conserva para reintentar
    });
  }

  otra() {
    this.confirmacion.set(null);
    this.claveVisible.set(null);
    this.form.reset({ producto_id: null, cantidad: 1, plazo_meses: 12 });
  }
}
