import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService } from './auth.service';

export const autenticado: CanActivateFn = (_r, state) => {
  const auth = inject(AuthService);
  if (auth.vigente()) return true;
  auth.aviso.set(auth.sesion() ? 'Tu sesión venció. Inicia sesión de nuevo.' : null);
  return inject(Router).createUrlTree(['/login'], { queryParams: { volver: state.url } });
};

/** Las vistas son una comodidad: la autorización real siempre se valida en el backend. */
export const soloAdmin: CanActivateFn = () => (inject(AuthService).esAdmin() ? true : inject(Router).createUrlTree(['/']));
export const soloCliente: CanActivateFn = () => (inject(AuthService).esCliente() ? true : inject(Router).createUrlTree(['/']));
