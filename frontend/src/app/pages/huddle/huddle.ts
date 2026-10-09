import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  selector: 'sh-huddle',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: '<p>Coming next.</p>',
})
export class HuddlePage {}
