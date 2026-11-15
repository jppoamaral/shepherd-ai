import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import type { AskDraft } from '../../api/types';
import { Icon } from '../../ui/icon';

/**
 * One drafted 1:1 message in an answer: read it, edit it, copy it, or send it.
 * Nothing goes out until the leader taps Send; the page owns the text and sends it.
 */
@Component({
  selector: 'sh-ask-draft',
  imports: [FormsModule, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styles: `
    :host { display: block; }
    .draft {
      display: flex; flex-direction: column; gap: var(--space-2);
      background: var(--cream); border: 1px solid var(--line); border-radius: var(--radius-md); padding: var(--space-3);
    }
    .draft > .sh-tag { align-self: flex-start; }
    .draft textarea {
      font: 400 16px/24px var(--font-sans); color: var(--ink); width: 100%;
      border: 1.5px solid var(--line-strong); border-radius: var(--radius-md);
      background: var(--paper); padding: var(--space-2) var(--space-3); resize: vertical;
    }
    .why-not { font-size: 14px; line-height: 20px; }
    .sh-btn.idle { opacity: .6; cursor: progress; }
  `,
  template: `
    @let d = draft();
    <div class="draft">
      @if (sent()) {
        <span class="sh-tag sh-tag--ok"><sh-icon name="check" />Sent · 1:1</span>
      } @else {
        <span class="sh-tag sh-tag--soft"><sh-icon name="pencil" />Draft · not sent</span>
      }
      @if (!alone()) {
        <span class="sh-cap">To {{ d.to }}</span>
      }
      @if (editing() && !sent()) {
        <label class="stack">
          <span class="visually-hidden">Message to {{ d.to }}</span>
          <textarea rows="4" [ngModel]="body()" (ngModelChange)="bodyChange.emit($event)"></textarea>
        </label>
      } @else {
        <p>{{ body() }}</p>
      }
      @if (d.replaces && !sent()) {
        <p class="sh-muted why-not">For {{ d.replaces }}'s place. If {{ first() }} says yes, you can swap them in from Home.</p>
      }
      @if (d.why_not && !sent()) {
        <p class="sh-muted why-not">{{ d.why_not }}</p>
      }
      <div class="sh-actions">
        @if (alone() && d.can_send && !sent()) {
          <button type="button" class="sh-btn sh-btn--primary" [class.idle]="sendingAny()"
                  [attr.aria-disabled]="sendingAny()" (click)="send.emit()">
            <sh-icon name="send" />{{ sending() ? 'Sending…' : 'Send to ' + first() }}
          </button>
        }
        @if (!sent()) {
          <button type="button" class="sh-btn sh-btn--secondary" (click)="toggleEdit.emit()"
                  [attr.aria-label]="(editing() ? 'Done editing' : 'Edit') + ' the message to ' + d.to">
            <sh-icon [name]="editing() ? 'check' : 'pencil'" />{{ editing() ? 'Done' : 'Edit' }}
          </button>
        }
        <button type="button" class="sh-btn sh-btn--secondary" (click)="copy.emit()"
                [attr.aria-label]="'Copy the message to ' + d.to">
          <sh-icon [name]="copied() ? 'check' : 'copy'" />{{ copied() ? 'Copied' : 'Copy' }}
        </button>
      </div>
    </div>
  `,
})
export class AskDraftCard {
  readonly draft = input.required<AskDraft>();
  /** The text as the leader has it now (edited or as drafted). */
  readonly body = input.required<string>();
  /** The only draft in its answer: it gets its own Send button and no "To" line. */
  readonly alone = input(false);
  readonly sent = input(false);
  readonly editing = input(false);
  readonly copied = input(false);
  /** This answer's drafts are being sent; any answer's drafts are being sent. */
  readonly sending = input(false);
  readonly sendingAny = input(false);

  readonly bodyChange = output<string>();
  readonly toggleEdit = output<void>();
  readonly copy = output<void>();
  readonly send = output<void>();

  protected readonly first = computed(() => this.draft().to.split(' ')[0]);
}
