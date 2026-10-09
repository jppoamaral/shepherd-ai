import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { ApiService } from '../../api/api.service';
import type { Church, Leader } from '../../api/types';
import { Session } from '../../core/session';
import { initials } from '../../core/format';
import { Icon } from '../../ui/icon';

/** "Who are you?" There's no login in the demo; leaders pick themselves. */
@Component({
  selector: 'sh-pick',
  imports: [Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    .wrap { min-height: 100vh; display: grid; place-items: center; padding: var(--space-5) var(--space-4); }
    .who { width: 100%; max-width: 480px; }
    .person { width: 100%; justify-content: flex-start; gap: var(--space-3); padding: var(--space-2) var(--space-4);
      min-height: 64px; border-radius: var(--radius-md); text-align: left; }
    .person-text { display: flex; flex-direction: column; }
    .person-name { font: 600 19px/26px var(--font-serif); color: var(--forest); }
    .brand { display: flex; align-items: center; gap: var(--space-2); }
    .logo { display: inline-flex; width: 32px; height: 32px; border-radius: var(--radius-pill);
      background: var(--forest); color: var(--on-forest); align-items: center; justify-content: center; }
    select { min-height: var(--tap-min); border-radius: var(--radius-pill); border: 1.5px solid var(--line-strong);
      background: var(--paper); color: var(--forest); font: 600 14px/20px var(--font-sans); padding: 0 var(--space-4); }
  `,
  template: `
    <main class="wrap">
      <div class="sh-card who">
        <div class="sh-wordmark brand"><span class="logo"><sh-icon name="logo" /></span>Shepherd</div>
        <h1 class="t-h1">Who's leading today?</h1>
        <p class="sh-muted">Pick yourself to see your week. This demo has no sign-in yet; all names are fictional.</p>
        @if (churches().length > 1) {
          <label class="stack">
            <span class="t-label">Church</span>
            <select [value]="churchId()" (change)="pickChurch($any($event.target).value)">
              @for (c of churches(); track c.id) {
                <option [value]="c.id">{{ c.name }}</option>
              }
            </select>
          </label>
        }
        @if (error()) {
          <p class="error-text" role="alert">{{ error() }}</p>
        }
        <div class="stack" role="list">
          @for (leader of leaders(); track leader.person_id) {
            <button type="button" class="sh-btn sh-btn--secondary person" role="listitem" (click)="choose(leader)">
              <span class="avatar">{{ initials(leader.name) }}</span>
              <span class="person-text">
                <span class="person-name">{{ leader.name }}</span>
                <span class="sh-cap">{{ duties(leader) }}</span>
              </span>
            </button>
          } @empty {
            @if (!error()) {
              <div role="status" class="stack"><div class="sh-skel"></div><div class="sh-skel"></div></div>
            }
          }
        </div>
      </div>
    </main>
  `,
})
export class PickPage {
  private readonly api = inject(ApiService);
  private readonly session = inject(Session);
  private readonly router = inject(Router);

  protected readonly churches = signal<Church[]>([]);
  protected readonly churchId = signal('');
  protected readonly leaders = signal<Leader[]>([]);
  protected readonly error = signal('');
  protected readonly initials = initials;

  constructor() {
    this.api.churches().subscribe({
      next: (churches) => {
        this.churches.set(churches);
        const grace = churches.find((c) => c.name === 'Grace Community') ?? churches[0];
        if (grace) this.pickChurch(grace.id);
      },
      error: () => this.error.set("Shepherd's server isn't reachable. Is it running on port 8000?"),
    });
  }

  protected pickChurch(id: string): void {
    this.churchId.set(id);
    this.leaders.set([]);
    this.api.leaders(id).subscribe((leaders) => this.leaders.set(leaders));
  }

  protected duties(leader: Leader): string {
    return leader.ministries
      .map((m) => `${m.ministry} ${m.can_schedule && m.can_approve ? 'coordinator' : m.can_schedule ? 'scheduler' : 'approver'}`)
      .join(' · ');
  }

  protected choose(leader: Leader): void {
    const church = this.churches().find((c) => c.id === this.churchId());
    if (!church) return;
    this.session.signIn({
      churchId: church.id,
      churchName: church.name,
      timezone: church.timezone,
      leader,
      ministryId: leader.ministries[0].ministry_id,
    });
    void this.router.navigate(['/']);
  }
}
