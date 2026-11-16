import { Component, EventEmitter, Input, Output } from '@angular/core';

/** Mensaje de error o éxito, con botón de reintento opcional (estado recuperable, sin simular éxitos). */
@Component({
  selector: 'app-aviso',
  standalone: true,
  template: `
    @if (texto) {
      <div class="aviso" [class.ok]="tipo === 'ok'" [class.error]="tipo === 'error'" role="alert">
        <span>{{ texto }}</span>
        @if (reintentar.observed) { <button type="button" class="link" (click)="reintentar.emit()">Reintentar</button> }
      </div>
    }
  `,
})
export class AvisoComponent {
  @Input() texto: string | null = null;
  @Input() tipo: 'error' | 'ok' | 'info' = 'error';
  @Output() reintentar = new EventEmitter<void>();
}
