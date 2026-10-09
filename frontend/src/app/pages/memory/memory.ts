import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  selector: 'sh-memory',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: '<p>Coming next.</p>',
})
export class MemoryPage {}
