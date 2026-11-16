import { Component, inject } from '@angular/core';
import { Router } from '@angular/router';

import { AuthService } from '../core/auth.service';

/** Redirige a la pantalla principal de cada rol. */
@Component({ selector: 'app-inicio', standalone: true, template: '' })
export class InicioComponent {
  constructor() {
    inject(Router).navigate([inject(AuthService).esAdmin() ? '/admin/prestamos' : '/solicitar'], { replaceUrl: true });
  }
}
