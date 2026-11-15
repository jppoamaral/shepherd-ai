import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import type { Proposal } from '../../api/types';
import { Icon } from '../../ui/icon';

/** How many reminders will actually go out (the server leaves out places that changed). */
export function reminderCount(p: Proposal): number {
  return p.count ?? (p.payload['messages'] as unknown[] | undefined)?.length ?? 0;
}

/** Something waiting for approval: a roster, a set of reminders or a memory suggestion. */
@Component({
  selector: 'sh-proposal-card',
  imports: [Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './cards.css',
  template: `
    @let p = proposal();
    @switch (p.type) {
      @case ('leader_roster') {
        <article class="sh-card">
          <div class="sh-brief-head">
            <span class="sh-tag sh-tag--soft"><sh-icon name="calendar" />Ready to review</span>
          </div>
          <h3>{{ p.title }}</h3>
          <div class="sh-bubble summary">{{ p.summary }}</div>
          @if (canApprove()) {
            <div class="sh-actions">
              <button type="button" class="sh-btn sh-btn--primary" [disabled]="busy()" (click)="approve.emit()">
                Approve roster
              </button>
            </div>
          } @else {
            <p class="sh-note"><sh-icon name="clock" />Waiting for {{ approverNames() }} to approve.</p>
          }
        </article>
      }
      @case ('reminders') {
        <article class="sh-card">
          <div class="sh-brief-head">
            <span class="sh-tag sh-tag--soft"><sh-icon name="send" />Ready to review</span>
          </div>
          <h3>{{ p.title }}</h3>
          @if (reviewing()) {
            @for (block of messages(); track $index) {
              <div class="sh-bubble">{{ block }}</div>
            }
          } @else if (messages().length) {
            <div class="sh-bubble">{{ messages()[0] }}</div>
          }
          @if (notSending(); as note) {
            <p class="sh-note"><sh-icon name="alert" />{{ note }}</p>
          }
          <div class="sh-cap">Private 1:1 messages. Nothing is sent until you approve.</div>
          <div class="sh-actions">
            @if (count() === 0) {
              <p class="sh-muted">Nobody on this reminder list is still on the roster.</p>
            } @else if (!canApprove()) {
              <p class="sh-note"><sh-icon name="clock" />Waiting for {{ approverNames() }} to approve and send.</p>
            } @else if (reviewing()) {
              <button type="button" class="sh-btn sh-btn--primary" [disabled]="busy()" (click)="approve.emit()">
                <sh-icon name="send" />Send {{ count() }} {{ count() === 1 ? 'reminder' : 'reminders' }}
              </button>
              <button type="button" class="sh-btn sh-btn--quiet" (click)="review.emit(false)">Not yet</button>
            } @else {
              <button type="button" class="sh-btn sh-btn--primary" (click)="review.emit(true)">
                <sh-icon name="send" />Review and send
              </button>
            }
          </div>
        </article>
      }
      @case ('memory') {
        <article class="sh-card sh-card--suggest">
          <div class="sh-sugg-label"><span class="sh-spark"><sh-icon name="spark" /></span>Memory suggestion</div>
          <p>{{ p.payload['text'] }} Remember this?</p>
          <div class="sh-actions">
            <button type="button" class="sh-btn sh-btn--primary" [disabled]="busy()" (click)="approve.emit()">Remember</button>
            <button type="button" class="sh-btn sh-btn--quiet" [disabled]="busy()" (click)="reject.emit()">Not now</button>
          </div>
        </article>
      }
    }
  `,
})
export class ProposalCard {
  readonly proposal = input.required<Proposal>();
  /** Only a ministry's approvers can approve its rosters and send its reminders. */
  readonly canApprove = input(false);
  readonly approverNames = input('an approver');
  readonly busy = input(false);
  /** Reminders: whether every message is expanded for review. */
  readonly reviewing = input(false);
  readonly approve = output<void>();
  readonly reject = output<void>();
  readonly review = output<boolean>();

  protected readonly count = computed(() => reminderCount(this.proposal()));
  /** The card's blocks: one message per person, then any "Not sending to …" note. */
  private readonly blocks = computed(() => (this.proposal().summary ?? '').split('\n\n'));
  protected readonly messages = computed(() => this.blocks().filter((b) => b.startsWith('To ')));
  protected readonly notSending = computed(() => {
    const notes = this.blocks().filter((b) => b.startsWith('Not sending'));
    return notes.length ? notes.join(' ') : undefined;
  });
}
