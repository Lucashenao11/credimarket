import { HttpErrorResponse } from '@angular/common/http';

/** Convierte cualquier error de las APIs en un mensaje claro para la persona usuaria. */
export function mensajeDeError(e: unknown): string {
  if (!(e instanceof HttpErrorResponse)) return 'Ocurrió un error inesperado.';
  if (e.status === 0) return 'No se pudo conectar con el servidor. Revisa que los servicios estén en marcha e inténtalo de nuevo.';
  const detalle = e.error?.detail;
  const texto = typeof detalle === 'string' ? detalle
    : Array.isArray(detalle) ? detalle.map((d: { loc?: string[]; msg: string }) => `${(d.loc ?? []).slice(1).join('.')}: ${d.msg}`).join('; ')
    : '';
  switch (e.status) {
    case 400: return texto || 'La solicitud no es válida.';
    case 401: return texto || 'Tu sesión no es válida o venció. Inicia sesión de nuevo.';
    case 403: return texto || 'No tienes permiso para esta operación.';
    case 404: return texto || 'No se encontró lo que buscabas.';
    case 409: return texto || 'La operación entra en conflicto con el estado actual.';
    case 422: return texto || 'Hay datos inválidos en el formulario.';
    case 503: return texto || 'Un servicio no está disponible en este momento. Inténtalo de nuevo en unos segundos.';
    default: return texto || `El servidor respondió con un error (${e.status}).`;
  }
}

/** Genera un identificador único; usa un respaldo si el navegador no ofrece crypto.randomUUID (p. ej. HTTP sin localhost). */
export function nuevoUuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}
