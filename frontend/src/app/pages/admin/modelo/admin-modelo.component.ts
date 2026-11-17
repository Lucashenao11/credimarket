import { Component, computed, inject, signal } from '@angular/core';
import { DecimalPipe, PercentPipe } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { ApiService } from '../../../core/api.service';
import { ConfigService } from '../../../core/config.service';
import { mensajeDeError } from '../../../core/errores';
import { ModeloInfo, Prestamo, RiesgoIn, RiesgoOut } from '../../../core/models';
import { AvisoComponent } from '../../../shared/aviso.component';
import { CopPipe, FechaPipe } from '../../../shared/formato';

const TASA_MENSUAL = 0.018; // la misma de Préstamos (contrato 4.3)
const LIMITE = 200;          // máximo que permite GET /prestamos

/** Métricas del manifiesto que se muestran, en este orden (claves "validacion_x" y "prueba_x"). */
const METRICAS: [string, string][] = [
  ['average_precision', 'Average precision (selección)'], ['roc_auc', 'ROC-AUC'], ['brier', 'Brier (menor es mejor)'],
  ['precision', 'Precisión (clase 1)'], ['recall', 'Recall (clase 1)'], ['f1', 'F1 (clase 1)'],
  ['tasa_rechazo', 'Tasa de rechazo'], ['costo_por_solicitud', 'Costo por solicitud (FN=3, FP=1)'],
];

interface UsoVersion { version: string; n: number; media: number; riesgoAlto: number; aprobadas: number; }

/**
 * Modelo (administrador).
 * - Versión activa, umbral, enlace directo al run de MLflow, métricas de validación y prueba, variables.
 * - Historial de promociones y rollbacks (si Préstamos lo expone en /modelo/info).
 * - Estadísticas de uso calculadas con las últimas solicitudes reales (GET /prestamos).
 * - Predicción manual con POST /riesgo/predict (no crea préstamos ni reserva inventario).
 */
@Component({
  selector: 'app-admin-modelo',
  standalone: true,
  imports: [AvisoComponent, FechaPipe, CopPipe, DecimalPipe, PercentPipe, ReactiveFormsModule],
  styles: [`
    .resumen { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:.8rem; margin:.6rem 0 1rem; }
    .dato { background:var(--papel); border-radius:6px; padding:.6rem .8rem; }
    .dato small { display:block; color:var(--suave); }
    .dato b { font:700 1.35rem var(--titulo); color:var(--petroleo); }
    .dos { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:0 1rem; }
    .dos label { margin:.4rem 0; }
    .resultado { font:700 1.5rem var(--titulo); }
    .alto { color:var(--mal); } .favorable { color:var(--ok); }
    .barra-uso { height:.55rem; background:var(--linea); border-radius:999px; overflow:hidden; min-width:80px; }
    .barra-uso span { display:block; height:100%; background:var(--mal); }
    code { word-break:break-all; }
  `],
  template: `
    <h1>Modelo de riesgo</h1>
    <app-aviso [texto]="error()" (reintentar)="cargar()" />

    @if (info(); as m) {
      <section class="tarjeta">
        <div class="resumen">
          <div class="dato"><small>Versión activa</small><b>{{ m.model_version }}</b></div>
          <div class="dato"><small>Umbral de decisión</small><b>{{ m.umbral }}</b></div>
          <div class="dato"><small>Promovida</small>{{ m.promovido_en | fecha }}</div>
        </div>
        <p>Probabilidad ≥ {{ m.umbral }} → <b class="alto">RIESGO_ALTO</b> (se rechaza); menor → <b class="favorable">FAVORABLE</b>.</p>
        <p class="nota">Run de MLflow: <code>{{ m.run_id ?? '—' }}</code><br />Hash del dataset: <code>{{ m.dataset_sha256 ?? '—' }}</code></p>
        <div class="acciones">
          @if (m.run_id) { <a class="boton" [href]="cfg.cfg.mlflow + '/#/runs/' + m.run_id" target="_blank" rel="noopener">Ver el run activo en MLflow</a> }
          <a class="boton" [href]="cfg.cfg.mlflow" target="_blank" rel="noopener" style="background:var(--petroleo-2)">Abrir MLflow</a>
        </div>
      </section>

      @if (filasMetricas().length) {
        <h2>Métricas</h2>
        <div class="tabla-caja"><table>
          <thead><tr><th>Métrica</th><th>Validación</th><th>Prueba (usada una vez)</th></tr></thead>
          <tbody>
            @for (f of filasMetricas(); track f.clave) {
              <tr><td>{{ f.nombre }}</td><td>{{ f.val ?? '—' }}</td><td>{{ f.prueba ?? '—' }}</td></tr>
            }
          </tbody>
        </table></div>
        @if (otrasMetricas().length) {
          <p class="nota">Otras: @for (o of otrasMetricas(); track o[0]) { {{ o[0] }} = {{ o[1] }}; }</p>
        }
      }

      <h2>Historial de versiones promovidas</h2>
      @if (m.historial?.length) {
        <div class="tabla-caja"><table>
          <thead><tr><th>Fecha</th><th>Acción</th><th>De</th><th>A</th><th>Por</th><th>Motivo</th></tr></thead>
          <tbody>
            @for (h of historialReciente(); track h.en) {
              <tr><td>{{ h.en | fecha }}</td><td>{{ h.accion }}</td><td>{{ h.desde ?? '—' }}</td><td><b>{{ h.model_version }}</b></td>
                  <td>{{ h.por }}</td><td style="white-space:normal">{{ h.motivo }}</td></tr>
            }
          </tbody>
        </table></div>
      } @else {
        <p class="nota">Préstamos todavía no devuelve el historial en <code>/modelo/info</code>
          (vive en <code>ml/registry/active.json</code>, lo escribe <code>ml/scripts/promover.py</code>).</p>
      }

      <h2>Uso del modelo</h2>
      <app-aviso [texto]="errorUso()" (reintentar)="cargarUso()" />
      @if (uso(); as u) {
        <p class="nota">Calculado con las últimas {{ u.total }} solicitudes registradas en Préstamos
          ({{ u.evaluadas }} pasaron por el modelo; las demás se decidieron antes, por reglas de negocio).</p>
        <div class="tabla-caja"><table>
          <thead><tr><th>Versión</th><th>Solicitudes evaluadas</th><th>Probabilidad media</th><th>Riesgo alto</th><th></th><th>Siguieron el flujo</th></tr></thead>
          <tbody>
            @for (v of u.porVersion; track v.version) {
              <tr>
                <td><b>{{ v.version }}</b> @if (v.version === m.model_version) { <small>(activa)</small> }</td>
                <td>{{ v.n }}</td><td>{{ v.media | number: '1.3-3' }}</td>
                <td>{{ v.riesgoAlto }} ({{ v.riesgoAlto / v.n | percent: '1.0-1' }})</td>
                <td><div class="barra-uso"><span [style.width.%]="100 * v.riesgoAlto / v.n"></span></div></td>
                <td>{{ v.aprobadas }}</td>
              </tr>
            } @empty { <tr><td colspan="6" class="vacio">Todavía no hay solicitudes evaluadas por el modelo.</td></tr> }
          </tbody>
        </table></div>
      } @else if (!errorUso()) { <p>Cargando…</p> }

      <h2>Predicción manual</h2>
      <form class="tarjeta" [formGroup]="form" (ngSubmit)="predecir()">
        <p class="nota" style="margin-top:0">Llama a <code>POST /riesgo/predict</code> con las 11 variables del contrato. No crea préstamos
          ni reserva inventario. Los campos opcionales vacíos se envían como faltantes (el pipeline los imputa).</p>
        <div class="dos">
          <label>Ingresos mensuales (COP) <input type="number" formControlName="ingresos_mensuales_cop" min="1" /></label>
          <label>Obligaciones mensuales (COP) <input type="number" formControlName="obligaciones_mensuales_cop" min="0" /></label>
          <label>Tipo de empleo
            <select formControlName="tipo_empleo">
              <option [ngValue]="null">(sin dato)</option>
              <option value="dependiente">dependiente</option><option value="independiente">independiente</option>
              <option value="temporal">temporal</option>
            </select>
          </label>
          <label>Antigüedad laboral (meses, opcional) <input type="number" formControlName="antiguedad_laboral_meses" min="0" /></label>
          <label>Historial crediticio (meses, opcional) <input type="number" formControlName="meses_historial_crediticio" min="0" /></label>
          <label>Créditos previos <input type="number" formControlName="creditos_previos" min="0" step="1" /></label>
          <label>Atrasos previos de 30 días <input type="number" formControlName="atrasos_previos_30d" min="0" step="1" /></label>
          <label>Pago puntual (%, opcional) <input type="number" formControlName="porcentaje_pago_puntual" min="0" max="100" /></label>
          <label>Monto solicitado (COP) <input type="number" formControlName="monto_solicitado_cop" min="1" /></label>
          <label>Plazo
            <select formControlName="plazo_meses">@for (p of plazos; track p) { <option [ngValue]="p">{{ p }} meses</option> }</select>
          </label>
        </div>
        <p>Cuota estimada (calculada con la fórmula del contrato): <b>{{ cuota() | cop }}</b></p>
        @if (form.touched && form.invalid) { <small class="err">Revisa los campos: importes positivos, conteos enteros ≥ 0, pago puntual entre 0 y 100.</small> }
        <app-aviso [texto]="errorPrediccion()" />
        <button type="submit" [disabled]="prediciendo()">{{ prediciendo() ? 'Calculando…' : 'Calcular riesgo' }}</button>
        @if (resultado(); as r) {
          <p style="margin-top:1rem">Probabilidad de incumplimiento:
            <span class="resultado" [class.alto]="r.decision === 'RIESGO_ALTO'" [class.favorable]="r.decision !== 'RIESGO_ALTO'">
              {{ r.probabilidad_incumplimiento | number: '1.4-4' }}</span>
            → <b>{{ r.decision }}</b> (umbral {{ r.umbral }}, modelo {{ r.model_version }})</p>
        }
      </form>
    } @else if (!error()) { <p>Cargando…</p> }
  `,
})
export class AdminModeloComponent {
  private api = inject(ApiService);
  cfg = inject(ConfigService);
  readonly plazos = [6, 12, 18, 24, 36];

  info = signal<ModeloInfo | null>(null);
  error = signal<string | null>(null);
  prestamos = signal<Prestamo[] | null>(null);
  errorUso = signal<string | null>(null);
  resultado = signal<RiesgoOut | null>(null);
  errorPrediccion = signal<string | null>(null);
  prediciendo = signal(false);

  // Valores iniciales: el ejemplo_entrada.json de v1 (una solicitud real de la partición de prueba)
  form = inject(FormBuilder).group({
    ingresos_mensuales_cop: [1753000 as number | null, [Validators.required, Validators.min(1)]],
    obligaciones_mensuales_cop: [825000 as number | null, [Validators.required, Validators.min(0)]],
    tipo_empleo: ['dependiente' as string | null],
    antiguedad_laboral_meses: [1 as number | null, Validators.min(0)],
    meses_historial_crediticio: [105 as number | null, Validators.min(0)],
    creditos_previos: [6 as number | null, [Validators.required, Validators.min(0), Validators.pattern(/^\d+$/)]],
    atrasos_previos_30d: [0 as number | null, [Validators.required, Validators.min(0), Validators.pattern(/^\d+$/)]],
    porcentaje_pago_puntual: [92.98 as number | null, [Validators.min(0), Validators.max(100)]],
    monto_solicitado_cop: [4484000 as number | null, [Validators.required, Validators.min(1)]],
    plazo_meses: [12, Validators.required],
  });
  private valores = signal(this.form.getRawValue());

  /** cuota = monto · i / (1 − (1 + i)^−n) */
  cuota = computed(() => {
    const v = this.valores();
    const monto = Number(v.monto_solicitado_cop) || 0, n = Number(v.plazo_meses);
    return (monto * TASA_MENSUAL) / (1 - Math.pow(1 + TASA_MENSUAL, -n));
  });

  filasMetricas = computed(() => {
    // Partial: un manifiesto puede no traer alguna métrica (v0-basico solo tiene dos de prueba; v2 no tiene de prueba)
    const m: Partial<Record<string, number>> = this.info()?.metricas ?? {};
    return METRICAS.map(([clave, nombre]) => ({ clave, nombre, val: m[`validacion_${clave}`], prueba: m[`prueba_${clave}`] }))
      .filter((f) => f.val != null || f.prueba != null);
  });
  /** Métricas con otro formato (p. ej. el manifiesto de v0-basico) */
  otrasMetricas = computed(() => {
    const m = this.info()?.metricas ?? {};
    const conocidas = new Set(METRICAS.flatMap(([c]) => [`validacion_${c}`, `prueba_${c}`]));
    return Object.entries(m).filter(([k]) => !conocidas.has(k));
  });
  historialReciente = computed(() => [...(this.info()?.historial ?? [])].reverse());

  uso = computed(() => {
    const lista = this.prestamos();
    if (!lista) return null;
    const evaluadas = lista.filter((p) => p.probabilidad_incumplimiento != null && p.modelo_version);
    const grupos = new Map<string, Prestamo[]>();
    evaluadas.forEach((p) => grupos.set(p.modelo_version!, [...(grupos.get(p.modelo_version!) ?? []), p]));
    const porVersion: UsoVersion[] = [...grupos.entries()].map(([version, ps]) => ({
      version, n: ps.length,
      media: ps.reduce((s, p) => s + p.probabilidad_incumplimiento!, 0) / ps.length,
      riesgoAlto: ps.filter((p) => p.motivo === 'RIESGO_ALTO').length,
      aprobadas: ps.filter((p) => p.estado !== 'RECHAZADA').length,
    })).sort((a, b) => b.n - a.n);
    return { total: lista.length, evaluadas: evaluadas.length, porVersion };
  });

  constructor() {
    this.form.valueChanges.subscribe(() => this.valores.set(this.form.getRawValue()));
    this.cargar();
  }

  cargar() {
    this.error.set(null);
    this.api.modeloInfo().subscribe({ next: (m) => this.info.set(m), error: (e) => this.error.set(mensajeDeError(e)) });
    this.cargarUso();
  }

  cargarUso() {
    this.errorUso.set(null);
    this.api.prestamos(LIMITE).subscribe({
      next: (p) => this.prestamos.set(p),
      error: (e) => this.errorUso.set(mensajeDeError(e)),
    });
  }

  predecir() {
    this.form.markAllAsTouched();
    if (this.form.invalid || this.prediciendo()) return;
    const v = this.form.getRawValue();
    const opcional = (x: number | null) => (x === null || (x as unknown) === '' ? null : Number(x));
    const datos: RiesgoIn = {
      ingresos_mensuales_cop: Number(v.ingresos_mensuales_cop), obligaciones_mensuales_cop: Number(v.obligaciones_mensuales_cop),
      tipo_empleo: v.tipo_empleo || null,
      antiguedad_laboral_meses: opcional(v.antiguedad_laboral_meses), meses_historial_crediticio: opcional(v.meses_historial_crediticio),
      creditos_previos: Number(v.creditos_previos), atrasos_previos_30d: Number(v.atrasos_previos_30d),
      porcentaje_pago_puntual: opcional(v.porcentaje_pago_puntual),
      monto_solicitado_cop: Number(v.monto_solicitado_cop), plazo_meses: Number(v.plazo_meses), cuota_estimada_cop: this.cuota(),
    };
    this.prediciendo.set(true);
    this.errorPrediccion.set(null);
    this.resultado.set(null);
    this.api.predecirRiesgo(datos).subscribe({
      next: (r) => { this.prediciendo.set(false); this.resultado.set(r); },
      error: (e) => { this.prediciendo.set(false); this.errorPrediccion.set(mensajeDeError(e)); },
    });
  }
}
