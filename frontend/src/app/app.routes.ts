import { Routes } from '@angular/router';

import { autenticado, soloAdmin, soloCliente } from './core/guards';

export const routes: Routes = [
  { path: 'login', loadComponent: () => import('./pages/login/login.component').then((m) => m.LoginComponent) },
  { path: '', pathMatch: 'full', loadComponent: () => import('./pages/inicio.component').then((m) => m.InicioComponent), canActivate: [autenticado] },
  { path: 'catalogo', loadComponent: () => import('./pages/catalogo/catalogo.component').then((m) => m.CatalogoComponent), canActivate: [autenticado] },
  { path: 'catalogo/:id', loadComponent: () => import('./pages/catalogo/producto-detalle.component').then((m) => m.ProductoDetalleComponent), canActivate: [autenticado] },
  { path: 'solicitar', loadComponent: () => import('./pages/solicitar/solicitar.component').then((m) => m.SolicitarComponent), canActivate: [autenticado, soloCliente] },
  { path: 'mis-prestamos', loadComponent: () => import('./pages/mis-prestamos/mis-prestamos.component').then((m) => m.MisPrestamosComponent), canActivate: [autenticado, soloCliente] },
  { path: 'perfil', loadComponent: () => import('./pages/perfil/perfil.component').then((m) => m.PerfilComponent), canActivate: [autenticado, soloCliente] },
  { path: 'admin/prestamos', loadComponent: () => import('./pages/admin/prestamos/admin-prestamos.component').then((m) => m.AdminPrestamosComponent), canActivate: [autenticado, soloAdmin] },
  { path: 'admin/inventario', loadComponent: () => import('./pages/admin/inventario/admin-inventario.component').then((m) => m.AdminInventarioComponent), canActivate: [autenticado, soloAdmin] },
  { path: 'admin/clientes', loadComponent: () => import('./pages/admin/clientes/admin-clientes.component').then((m) => m.AdminClientesComponent), canActivate: [autenticado, soloAdmin] },
  { path: 'admin/modelo', loadComponent: () => import('./pages/admin/modelo/admin-modelo.component').then((m) => m.AdminModeloComponent), canActivate: [autenticado, soloAdmin] },
  { path: '**', redirectTo: '' },
];
