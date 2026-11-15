import { Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { Waking } from './core/waking';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  styles: `
    .waking { position: fixed; left: 50%; bottom: var(--space-5); transform: translateX(-50%); z-index: 100;
      width: max-content; max-width: calc(100vw - 2 * var(--space-4)); box-shadow: 0 4px 16px rgb(0 0 0 / 12%); }
  `,
  template: `
    <router-outlet />
    @if (waking.slow()) {
      <p class="sh-notice sh-notice--info waking" role="status">
        Waking up Shepherd… The demo server sleeps when idle, so the first load can take about a minute.
      </p>
    }
  `,
})
export class App {
  protected readonly waking = inject(Waking);
}
