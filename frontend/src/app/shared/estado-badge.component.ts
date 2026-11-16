import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-estado',
  standalone: true,
  template: `<span class="badge" [class]="'badge ' + estado">{{ estado.replaceAll('_', ' ') }}</span>`,
})
export class EstadoBadgeComponent {
  @Input({ required: true }) estado = '';
}
