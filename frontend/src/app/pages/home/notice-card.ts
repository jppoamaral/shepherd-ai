import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import type { Notice } from '../../api/types';
import { Icon } from '../../ui/icon';

/** A decline, "can't commit" or "can serve" needs the leader until the place is dealt with. */
export function noticeNeedsLeader(n: Notice): boolean {
  return (n.kind === 'declined' || n.kind === 'cant_commit' || n.kind === 'can_serve') && !n.settled;
}

/** What a volunteer asked Shepherd to pass on to their leader, shown once on Home. */
@Component({
  selector: 'sh-notice-card',
  imports: [Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './cards.css',
  template: `
    <article class="sh-card" [attr.aria-labelledby]="'notice-' + notice().id">
      <div class="sh-brief-head">
        <span class="sh-tag sh-tag--attn"><sh-icon name="chat" />From {{ about() }}'s chat</span>
        <span class="sh-cap">{{ needsLeader() ? 'Needs you' : 'Good to know' }}</span>
      </div>
      <h3 [id]="'notice-' + notice().id">{{ notice().text }}</h3>
      @if (notice().update) {
        <p class="sh-tag sh-tag--ok"><sh-icon name="check" />{{ notice().update }}</p>
      }
      @if (notice().note) {
        <div class="sh-bubble">“{{ notice().note }}”</div>
        <p class="sh-note"><sh-icon name="lock" />{{ about() }} asked Shepherd to pass this on. It isn't kept: dismissing deletes it.</p>
      }
      <div class="sh-actions">
        @if (notice().put_in; as p) {
          <button type="button" class="sh-btn sh-btn--primary" [disabled]="busy()" (click)="putIn.emit()">
            Put {{ first(p.name) }} in{{ p.replaces ? ' for ' + first(p.replaces) : '' }}
          </button>
        }
        <button type="button" class="sh-btn sh-btn--secondary" (click)="dismiss.emit()">Dismiss</button>
      </div>
    </article>
  `,
})
export class NoticeCard {
  readonly notice = input.required<Notice>();
  readonly busy = input(false);
  /** Someone said yes when asked: put them in, through the approval queue. */
  readonly putIn = output<void>();
  /** Dismissing deletes the notice, including anything personal the volunteer passed on. */
  readonly dismiss = output<void>();

  protected readonly about = computed(() => this.first(this.notice().about));
  protected readonly needsLeader = computed(() => noticeNeedsLeader(this.notice()));

  protected first(name: string): string {
    return name.split(' ')[0];
  }
}
