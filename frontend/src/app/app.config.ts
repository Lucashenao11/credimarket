import { APP_INITIALIZER, ApplicationConfig, inject, provideZoneChangeDetection } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter } from '@angular/router';

import { routes } from './app.routes';
import { authInterceptor } from './core/auth.interceptor';
import { ConfigService } from './core/config.service';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes),
    provideHttpClient(withInterceptors([authInterceptor])),
    // Las URLs de las APIs se leen de /config.json ANTES de arrancar: cambiar de entorno no exige recompilar.
    { provide: APP_INITIALIZER, multi: true, useFactory: () => { const c = inject(ConfigService); return () => c.cargar(); } },
  ],
};
