import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';
import type { BriefingItem, GapFill } from '../../api/types';
import { monthDay } from '../../core/format';
import { Icon } from '../../ui/icon';

const EXPERIENCE: Record<string, string> = { new: 'New', experienced: 'Experienced', veteran: 'Veteran' };

/** One thing the checks found this week: a shared volunteer, someone rostered while away, someone serving a lot, an open slot. */
@Component({
  selector: 'sh-finding-card',
  imports: [RouterLink, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './cards.css',
  template: `
    @switch (item().type) {
      @case ('overlap') {
        <article class="sh-card">
          <div class="sh-brief-head">
            <span class="sh-tag sh-tag--attn"><sh-icon name="alert" />Shared volunteer</span>
            <span class="sh-cap">Needs you</span>
          </div>
          <h3>{{ overlapHeadline() }}</h3>
          <p>{{ item().text }} Shepherd won't move anyone.</p>
          @if (item().can_huddle) {
            <div class="sh-actions">
              <a class="sh-btn sh-btn--primary" [routerLink]="['/huddle', item().finding_id]">See options</a>
              <a class="sh-btn sh-btn--secondary" [routerLink]="['/huddle', item().finding_id]">Find a time to talk</a>
            </div>
          }
        </article>
      }
      @case ('blockout') {
        <article class="sh-card">
          <div class="sh-brief-head">
            <span class="sh-tag sh-tag--attn"><sh-icon name="calendar" />Away that day</span>
            <span class="sh-cap">Needs you</span>
          </div>
          <h3>{{ item().text }}</h3>
          <p>Shepherd won't move anyone. You can change the roster or check with them.</p>
          <div class="sh-actions">
            <a class="sh-btn sh-btn--secondary" routerLink="/rosters">See the roster</a>
          </div>
        </article>
      }
      @case ('load') {
        <article class="sh-card">
          <div class="sh-brief-head">
            <span class="sh-tag sh-tag--soft"><sh-icon name="clock" />Good to know</span>
            <span class="sh-cap">No action needed</span>
          </div>
          <h3>{{ split()[0] }}.</h3>
          <p>{{ split()[1] }} It may be worth a check-in before you ask again.</p>
        </article>
      }
      @case ('below_minimum') {
        <article class="sh-card">
          <div class="sh-brief-head">
            <span class="sh-tag sh-tag--soft"><sh-icon name="calendar" />Open slot</span>
            <span class="sh-cap">Needs you</span>
          </div>
          <h3>{{ item().text }}</h3>
          @if (item().fill; as f) {
            <p>{{ f.name }} ({{ experience[f.experience] }}) is free then and not blocked out.</p>
          }
          @if (item().fill && !canApprove()) {
            <p class="sh-note"><sh-icon name="clock" />{{ approverNames() }} can put them in. Nothing changes until an approver does.</p>
          }
          <div class="sh-actions">
            @if (item().fill; as f) {
              @if (canApprove()) {
                <button type="button" class="sh-btn sh-btn--primary" [disabled]="busy()" (click)="fill.emit(f)"
                        [attr.aria-label]="'Put ' + f.name + ' in as ' + f.role">
                  Put {{ f.name.split(' ')[0] }} in
                </button>
              }
            }
            <a class="sh-btn sh-btn--secondary" routerLink="/rosters">See options</a>
          </div>
        </article>
      }
    }
  `,
})
export class FindingCard {
  readonly item = input.required<BriefingItem>();
  /** Only a ministry's approvers can put someone in. */
  readonly canApprove = input(false);
  readonly approverNames = input('an approver');
  readonly busy = input(false);
  /** Fill the open slot with the person Shepherd found free. */
  readonly fill = output<GapFill>();

  protected readonly experience = EXPERIENCE;

  /** "Anna Parker is on Kids and Worship at the same time on Oct 11." */
  protected readonly overlapHeadline = computed(() => {
    const item = this.item();
    const where = item.ministries.length > 1 ? item.ministries.join(' and ') : `${item.ministries[0]} twice`;
    return `${item.people[0]} is on ${where} at the same time on ${monthDay(item.on)}.`;
  });

  /** The check's sentence split at its first comma: a short headline, then the details. */
  protected readonly split = computed<[string, string]>(() => {
    const text = this.item().text;
    const at = text.indexOf(', ');
    if (at < 0) return [text.replace(/\.$/, ''), ''];
    const rest = text.slice(at + 2);
    return [text.slice(0, at), rest.charAt(0).toUpperCase() + rest.slice(1)];
  });
}
