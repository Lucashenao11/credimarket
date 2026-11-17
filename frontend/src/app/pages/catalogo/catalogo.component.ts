import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { mensajeDeError } from '../../core/errores';
import { Producto, ProductoIn } from '../../core/models';
import { AvisoComponent } from '../../shared/aviso.component';
import { CopPipe } from '../../shared/formato';

/**
 * Catálogo.
 * - Todos: tarjetas con precio y versión; enlace al detalle.
 * - Cliente: botón "Solicitar a crédito".
 * - Administrador: crear, editar (PUT solo con los campos que cambian) y desactivar (DELETE = borrado lógico),
 *   con opción de ver los inactivos. Cada cambio sube la versión en el servidor; el aviso lo muestra.
 */
@Component({
  selector: 'app-catalogo',
  standalone: true,
  imports: [AvisoComponent, CopPipe, RouterLink, ReactiveFormsModule],
  styles: [`
    .version { font-size:.78rem; color:var(--suave); }
    .inactivo { opacity:.6; border-top-color:var(--suave) !important; }
    .etiqueta { display:inline-block; padding:.05rem .5rem; border-radius:999px; font-size:.75rem; font-weight:600;
                background:var(--mal-fondo); color:var(--mal); margin-left:.4rem; }
    .encabezado { display:flex; justify-content:space-between; align-items:center; gap:1rem; flex-wrap:wrap; }
    .encabezado label { flex-direction:row; align-items:center; margin:0; font-weight:400; }
    .tarjeta .acciones button { padding:.3rem .6rem; font-size:.85rem; }
    .rejilla .detalle { margin:.2rem 0 .6rem; font-size:.9rem; }
  `],
  template: `
    <div class="encabezado">
      <h1>Catálogo</h1>
      @if (auth.esAdmin()) {
        <div class="fila">
          <label><input type="checkbox" [checked]="verInactivos()" (change)="alternarInactivos()" /> Mostrar inactivos</label>
          @if (!formAbierto()) { <button type="button" (click)="nuevo()">Nuevo producto</button> }
        </div>
      }
    </div>

    <app-aviso [texto]="error()" (reintentar)="cargar()" />
    <app-aviso [texto]="exito()" tipo="ok" />

    @if (auth.esAdmin() && formAbierto()) {
      <form class="tarjeta estrecha" [formGroup]="form" (ngSubmit)="guardar()">
        <h2 style="margin-top:0">{{ editando() ? 'Editar producto #' + editando()!.id + ' (versión ' + editando()!.version + ')' : 'Nuevo producto' }}</h2>
        <label>Nombre <input formControlName="nombre" maxlength="120" /></label>
        @if (tocado('nombre')) { <small class="err">Entre 2 y 120 caracteres.</small> }
        <label>Categoría <input formControlName="categoria" maxlength="60" /></label>
        @if (tocado('categoria')) { <small class="err">Entre 2 y 60 caracteres.</small> }
        <label>Precio (COP) <input type="number" formControlName="precio_cop" min="1" step="1000" /></label>
        @if (tocado('precio_cop')) { <small class="err">El precio debe ser un entero mayor que cero.</small> }
        <div class="acciones">
          <button type="submit" [disabled]="guardando()">{{ guardando() ? 'Guardando…' : (editando() ? 'Guardar cambios' : 'Crear producto') }}</button>
          <button type="button" class="link" (click)="cerrarForm()">Cancelar</button>
        </div>
      </form>
    }

    @if (cargando()) { <p>Cargando…</p> }
    <div class="rejilla">
      @for (p of productos(); track p.id) {
        <article class="tarjeta" [class.inactivo]="!p.activo">
          <small>{{ p.categoria }} @if (!p.activo) { <span class="etiqueta">Inactivo</span> }</small>
          <h3>{{ p.nombre }}</h3>
          <p class="precio">{{ p.precio_cop | cop }}</p>
          <span class="version">Versión {{ p.version }}</span>
          <a class="detalle" [routerLink]="['/catalogo', p.id]">Ver detalle</a>
          @if (auth.esCliente() && p.activo) {
            <a class="boton" [routerLink]="['/solicitar']" [queryParams]="{ producto: p.id }">Solicitar a crédito</a>
          }
          @if (auth.esAdmin() && p.activo) {
            <div class="acciones">
              <button type="button" class="link" (click)="editar(p)">Editar</button>
              @if (confirmando() === p.id) {
                <button type="button" class="peligro" [disabled]="desactivando()" (click)="desactivar(p)">
                  {{ desactivando() ? 'Desactivando…' : 'Confirmar' }}</button>
                <button type="button" class="link" (click)="confirmando.set(null)">No</button>
              } @else {
                <button type="button" class="link" (click)="confirmando.set(p.id)">Desactivar</button>
              }
            </div>
          }
        </article>
      } @empty {
        @if (!cargando() && !error()) { <p class="vacio">No hay productos {{ verInactivos() ? '' : 'activos' }}.</p> }
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
  exito = signal<string | null>(null);
  verInactivos = signal(false);

  formAbierto = signal(false);
  editando = signal<Producto | null>(null);
  guardando = signal(false);
  confirmando = signal<number | null>(null);
  desactivando = signal(false);

  form = inject(FormBuilder).nonNullable.group({
    nombre: ['', [Validators.required, Validators.minLength(2), Validators.maxLength(120)]],
    categoria: ['', [Validators.required, Validators.minLength(2), Validators.maxLength(60)]],
    precio_cop: [0, [Validators.required, Validators.min(1), Validators.pattern(/^\d+$/)]],
  });

  constructor() { this.cargar(); }

  cargar() {
    this.cargando.set(true);
    this.error.set(null);
    this.api.productos(!this.verInactivos()).subscribe({
      next: (p) => { this.productos.set(p); this.cargando.set(false); },
      error: (e) => { this.error.set(mensajeDeError(e)); this.cargando.set(false); },
    });
  }

  alternarInactivos() { this.verInactivos.update((v) => !v); this.cargar(); }

  tocado(campo: 'nombre' | 'categoria' | 'precio_cop') {
    const c = this.form.controls[campo];
    return c.invalid && (c.touched || c.dirty);
  }

  nuevo() {
    this.editando.set(null);
    this.form.reset({ nombre: '', categoria: '', precio_cop: 0 });
    this.exito.set(null);
    this.formAbierto.set(true);
  }

  editar(p: Producto) {
    this.editando.set(p);
    this.form.reset({ nombre: p.nombre, categoria: p.categoria, precio_cop: p.precio_cop });
    this.exito.set(null);
    this.formAbierto.set(true);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  cerrarForm() { this.formAbierto.set(false); this.editando.set(null); }

  guardar() {
    this.form.markAllAsTouched();
    if (this.form.invalid || this.guardando()) return; // sin envíos duplicados
    const v: ProductoIn = { ...this.form.getRawValue(), precio_cop: Number(this.form.getRawValue().precio_cop) };
    const actual = this.editando();
    this.error.set(null);
    this.exito.set(null);

    if (actual) {
      // PUT solo con lo que cambió: si no cambia nada, el servidor no sube la versión
      const cambios: Partial<ProductoIn> = {};
      (Object.keys(v) as (keyof ProductoIn)[]).forEach((k) => {
        if (v[k] !== actual[k]) (cambios as Record<string, unknown>)[k] = v[k];
      });
      if (!Object.keys(cambios).length) { this.exito.set('No hay cambios que guardar.'); return; }
      this.guardando.set(true);
      this.api.actualizarProducto(actual.id, cambios).subscribe({
        next: (p) => this.listo(`"${p.nombre}" actualizado: versión ${actual.version} → ${p.version}.`),
        error: (e) => { this.guardando.set(false); this.error.set(mensajeDeError(e)); },
      });
    } else {
      this.guardando.set(true);
      this.api.crearProducto(v).subscribe({
        next: (p) => this.listo(`"${p.nombre}" creado con id ${p.id} (versión ${p.version}).`),
        error: (e) => { this.guardando.set(false); this.error.set(mensajeDeError(e)); },
      });
    }
  }

  desactivar(p: Producto) {
    if (this.desactivando()) return;
    this.desactivando.set(true);
    this.error.set(null);
    this.exito.set(null);
    this.api.desactivarProducto(p.id).subscribe({
      next: (r) => {
        this.desactivando.set(false);
        this.confirmando.set(null);
        this.exito.set(`"${r.nombre}" desactivado (versión ${p.version} → ${r.version}). Ya no se puede solicitar.`);
        this.cargar();
      },
      error: (e) => { this.desactivando.set(false); this.error.set(mensajeDeError(e)); },
    });
  }

  private listo(mensaje: string) {
    this.guardando.set(false);
    this.cerrarForm();
    this.exito.set(mensaje);
    this.cargar();
  }
}
