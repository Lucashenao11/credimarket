import { Pipe, PipeTransform } from '@angular/core';

@Pipe({ name: 'cop', standalone: true })
export class CopPipe implements PipeTransform {
  transform(v: number | null | undefined): string {
    return v == null ? '—' : new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 }).format(v);
  }
}

@Pipe({ name: 'fecha', standalone: true })
export class FechaPipe implements PipeTransform {
  transform(v: string | null | undefined): string {
    if (!v) return '—';
    // El backend entrega UTC; si llega sin zona horaria se interpreta como UTC
    const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(v) ? v : v + 'Z');
    return isNaN(d.getTime()) ? v : d.toLocaleString('es-CO', { dateStyle: 'short', timeStyle: 'medium' });
  }
}

export const EXPLICACION_ESTADO: Record<string, string> = {
  PENDIENTE_INVENTARIO: 'Riesgo favorable. Esperando que Inventario confirme las unidades. Todavía NO está aprobado.',
  APROBADA: 'Inventario confirmó la reserva. Queda pendiente la entrega.',
  RECHAZADA: 'La evaluación de riesgo o las reglas de negocio dieron una decisión desfavorable. No se reservó inventario.',
  CANCELADA_SIN_STOCK: 'No había unidades suficientes. Se canceló sin reservar nada.',
  CANCELADA: 'La solicitud se canceló y la reserva (si existía) se liberó.',
  COMPLETADA: 'Entrega registrada: Inventario confirmó la salida.',
};

export const MOTIVOS: Record<string, string> = {
  RIESGO_ALTO: 'Riesgo de incumplimiento por encima del umbral',
  CLIENTE_INACTIVO: 'Cliente inactivo',
  INFORMACION_INSUFICIENTE: 'Información financiera insuficiente',
  MONTO_FUERA_DE_RANGO: 'Monto fuera del rango permitido',
  SIN_STOCK: 'Sin existencias',
  TIMEOUT_INVENTARIO: 'Inventario no respondió a tiempo',
  RESERVA_VENCIDA: 'La reserva venció',
  CANCELADO_POR_USUARIO: 'Cancelada por el usuario',
};
