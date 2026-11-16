import { Component, inject, signal } from '@angular/core';
import { KeyValuePipe } from '@angular/common';

import { ApiService } from '../../../core/api.service';
import { ConfigService } from '../../../core/config.service';
import { mensajeDeError } from '../../../core/errores';
import { ModeloInfo } from '../../../core/models';
import { AvisoComponent } from '../../../shared/aviso.component';
import { FechaPipe } from '../../../shared/formato';

/**
 * Modelo — VERSIÓN BÁSICA (solo lectura de /modelo/info).
 * TODO(Juan David): estadísticas de uso (conteo por decisión, probabilidad media), historial de versiones
 * promovidas, enlace al run de MLflow de la versión activa y predicción manual (POST /riesgo/predict).
 */
@Component({
  selector: 'app-admin-modelo',
  standalone: true,
  imports: [AvisoComponent, FechaPipe, KeyValuePipe],
  template: `
    <h1>Modelo de riesgo</h1>
    <app-aviso [texto]="error()" (reintentar)="cargar()" />
    @if (info(); as m) {
      <section class="tarjeta">
        <p>Versión activa: <b>{{ m.model_version }}</b> · umbral {{ m.umbral }} · promovido {{ m.promovido_en | fecha }}</p>
        <p class="nota">Run de MLflow: <code>{{ m.run_id ?? '—' }}</code> · hash del dataset: <code>{{ m.dataset_sha256 ?? '—' }}</code></p>
        @if (m.metricas) { <ul>@for (k of m.metricas | keyvalue; track k.key) { <li>{{ k.key }}: {{ k.value }}</li> }</ul> }
        <h3>Variables ({{ m.features.length }})</h3>
        <ul>@for (f of m.features; track f.nombre) { <li>{{ f.nombre }} <small>({{ f.tipo }})</small></li> }</ul>
        <a class="boton" [href]="cfg.cfg.mlflow" target="_blank" rel="noopener">Abrir MLflow</a>
      </section>
    } @else if (!error()) { <p>Cargando…</p> }
  `,
})
export class AdminModeloComponent {
  private api = inject(ApiService);
  cfg = inject(ConfigService);
  info = signal<ModeloInfo | null>(null);
  error = signal<string | null>(null);

  constructor() { this.cargar(); }

  cargar() {
    this.error.set(null);
    this.api.modeloInfo().subscribe({ next: (m) => this.info.set(m), error: (e) => this.error.set(mensajeDeError(e)) });
  }
}
