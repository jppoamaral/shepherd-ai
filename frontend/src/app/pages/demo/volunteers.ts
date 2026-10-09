import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../api/api.service';
import type { Volunteer } from '../../api/types';
import { initials } from '../../core/format';
import { Icon } from '../../ui/icon';

/** Demo only: pick a volunteer to see their 1:1 chat with Shepherd. Volunteers never sign in. */
@Component({
  selector: 'sh-demo-volunteers',
  imports: [RouterLink, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    .wrap { min-height: 100vh; display: grid; place-items: center; padding: var(--space-5) var(--space-4); }
    .who { width: 100%; max-width: 480px; }
    .list { max-height: 60vh; overflow-y: auto; }
    .person { width: 100%; justify-content: flex-start; gap: var(--space-3); padding: var(--space-2) var(--space-4);
      min-height: 64px; border-radius: var(--radius-md); text-align: left; }
    .person-text { display: flex; flex-direction: column; flex: 1; }
    .person-name { font: 600 19px/26px var(--font-serif); color: var(--forest); }
    .back { align-self: flex-start; padding-left: 0; }
  `,
  template: `
    <main class="wrap">
      <div class="sh-card who">
        <a class="sh-btn sh-btn--quiet back" routerLink="/pick"><sh-icon name="back" />Back to leaders</a>
        <h1 class="t-h1">Open a volunteer's chat</h1>
        <p class="sh-muted">Demo only. Volunteers never use the app; in real life this is their Telegram chat with Shepherd.</p>
        <div class="stack list" role="list">
          @for (v of ordered(); track v.person_id) {
            <a class="sh-btn sh-btn--secondary person" role="listitem"
               [routerLink]="['/demo/chat', v.person_id]" [queryParams]="{ church: church() }">
              <span class="avatar">{{ initials(v.name) }}</span>
              <span class="person-text">
                <span class="person-name">{{ v.name }}</span>
                <span class="sh-cap">{{ v.ministries.join(' · ') }}</span>
              </span>
              @if (v.stopped) {
                <span class="sh-tag sh-tag--soft">Reminders off</span>
              } @else if (!v.connected) {
                <span class="sh-tag sh-tag--soft">Not connected</span>
              }
            </a>
          } @empty {
            <div role="status" class="stack"><div class="sh-skel"></div><div class="sh-skel"></div></div>
          }
        </div>
      </div>
    </main>
  `,
})
export class DemoVolunteersPage {
  /** Query parameter: the church picked on "Who's leading today?". */
  readonly church = input<string>('');
  private readonly api = inject(ApiService);
  protected readonly volunteers = signal<Volunteer[]>([]);
  protected readonly initials = initials;
  /** Anna Parker first: she's in the demo script. */
  protected readonly ordered = computed(() =>
    [...this.volunteers()].sort((a, b) => Number(b.name === 'Anna Parker') - Number(a.name === 'Anna Parker')),
  );

  constructor() {
    effect(() => {
      const church = this.church();
      if (church) this.api.volunteers(church).subscribe((v) => this.volunteers.set(v));
    });
  }
}
