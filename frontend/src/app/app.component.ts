import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { AuthService } from './core/auth.service';
import { ConfigService } from './core/config.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <header class="barra">
      <a routerLink="/" class="marca">CrediMarket</a>
      @if (auth.sesion(); as s) {
        <nav>
          <a routerLink="/catalogo" routerLinkActive="activo">Catálogo</a>
          @if (auth.esCliente()) {
            <a routerLink="/solicitar" routerLinkActive="activo">Solicitar</a>
            <a routerLink="/mis-prestamos" routerLinkActive="activo">Mis solicitudes</a>
            <a routerLink="/perfil" routerLinkActive="activo">Mi perfil</a>
          }
          @if (auth.esAdmin()) {
            <a routerLink="/admin/prestamos" routerLinkActive="activo">Préstamos</a>
            <a routerLink="/admin/inventario" routerLinkActive="activo">Inventario</a>
            <a routerLink="/admin/clientes" routerLinkActive="activo">Clientes</a>
            <a routerLink="/admin/modelo" routerLinkActive="activo">Modelo</a>
          }
        </nav>
        <div class="usuario">
          <span>{{ s.usuario }} <small class="rol">{{ s.rol }}</small></span>
          <button type="button" class="link" (click)="auth.logout()">Cerrar sesión</button>
        </div>
      }
    </header>
    <main><router-outlet /></main>
    <footer>
      <a [href]="cfg.cfg.mlflow" target="_blank" rel="noopener">MLflow</a> ·
      <a [href]="cfg.cfg.rabbitmq" target="_blank" rel="noopener">RabbitMQ</a>
    </footer>
  `,
})
export class AppComponent {
  auth = inject(AuthService);
  cfg = inject(ConfigService);
}
