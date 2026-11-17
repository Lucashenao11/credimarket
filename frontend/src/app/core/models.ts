export type Rol = 'cliente' | 'admin';

export interface Producto { id: number; nombre: string; categoria: string; precio_cop: number; version: number; activo: boolean; }
export interface ProductoIn { nombre: string; categoria: string; precio_cop: number; }

export interface Cliente {
  cliente_id: string; nombre: string | null; email: string | null; activo: boolean;
  ingresos_mensuales_cop: number; obligaciones_mensuales_cop: number; tipo_empleo: string | null;
  antiguedad_laboral_meses: number | null; meses_historial_crediticio: number | null;
  creditos_previos: number; atrasos_previos_30d: number; porcentaje_pago_puntual: number | null;
}

export interface ResultadoFila { fila: number; cliente_id: string | null; resultado: 'insertado' | 'ya_existia' | 'error'; detalle: string | null; }
export interface ReporteImportacion { archivo: string; total_filas: number; insertados: number; ya_existian: number; errores: number; filas: ResultadoFila[]; }

export interface Prestamo {
  id: string; cliente_id: string; producto_id: number; cantidad: number; plazo_meses: number;
  precio_unitario_cop: number; version_cotizacion: number; monto_cop: number; cuota_cop: number;
  probabilidad_incumplimiento: number | null; modelo_version: string | null; umbral: number | null;
  estado: string; motivo: string | null; creado_en: string; actualizado_en: string;
}
export interface Historial { estado_anterior: string | null; estado_nuevo: string; motivo: string | null; en: string; }
export interface SolicitudIn { producto_id: number; cantidad: number; plazo_meses: number; }

export interface Existencia { producto_id: number; disponible: number; reservado: number; actualizado_en: string | null; }
export interface Reserva { prestamo_id: string; producto_id: number; cantidad: number; estado: string; motivo: string | null; vence_en: string; creada_en: string | null; }
export interface Movimiento { producto_id: number; tipo: string; cantidad: number; prestamo_id: string | null; creado_en: string | null; }

export interface ModeloInfo {
  model_version: string; run_id: string | null; umbral: number; clase_positiva: number;
  features: { nombre: string; tipo: string }[]; metricas: Record<string, number> | null;
  dataset_sha256: string | null; promovido_en: string | null;
}
