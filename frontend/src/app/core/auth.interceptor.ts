import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

import { AuthService } from './auth.service';
import { ConfigService } from './config.service';

/** Agrega el token a las peticiones hacia nuestras APIs y cierra la sesión si el servidor responde 401. */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const cfg = inject(ConfigService);
  const esLogin = req.url.endsWith('/auth/login');
  const sesion = auth.sesion();
  if (cfg.esApi(req.url) && !esLogin && sesion) {
    req = req.clone({ setHeaders: { Authorization: `Bearer ${sesion.token}` } });
  }
  return next(req).pipe(
    catchError((e: HttpErrorResponse) => {
      if (e.status === 401 && !esLogin && sesion) auth.logout('Tu sesión venció. Inicia sesión de nuevo.');
      return throwError(() => e);
    }),
  );
};
