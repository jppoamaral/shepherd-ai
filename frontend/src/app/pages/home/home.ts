import { ChangeDetectionStrategy, Component, computed, effect, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../api/api.service';
import type { Briefing, BriefingItem, Proposal } from '../../api/types';
import { Session } from '../../core/session';
import { churchToday, longDate, monthDay } from '../../core/format';
import { Icon } from '../../ui/icon';

type CardKind = 'overlap' | 'load' | 'below_minimum';

/** Home: the weekly briefing for the current ministry, and what's waiting for approval. */
@Component({
  selector: 'sh-home',
  imports: [RouterLink, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './home.css',
  templateUrl: './home.html',
})
export class HomePage {
  private readonly api = inject(ApiService);
  protected readonly session = inject(Session);

  protected readonly briefing = signal<Briefing | null>(null);
  protected readonly proposals = signal<Proposal[]>([]);
  protected readonly loading = signal(true);
  protected readonly error = signal('');
  protected readonly busy = signal<string | null>(null);
  protected readonly queueMessage = signal('');

  /** Only what concerns the ministry being viewed. */
  protected readonly items = computed(() => {
    const ministry = this.session.ministry()?.ministry;
    return (this.briefing()?.items ?? []).filter((i) => !ministry || i.ministries.includes(ministry));
  });
  protected readonly memorySuggestions = computed(() =>
    this.proposals().filter((p) => p.type === 'memory' && p.payload['ministry_id'] === this.session.ministryId()),
  );
  protected readonly rosterProposals = computed(() =>
    this.proposals().filter((p) => p.type === 'leader_roster' && p.payload['ministry_id'] === this.session.ministryId()),
  );
  protected readonly nextGathering = computed(() => {
    const ministryId = this.session.ministryId();
    return this.briefing()?.gatherings.find((g) => g.ministry_id === ministryId && g.filled > 0) ?? null;
  });

  // SAMPLE: the absence check-in, reminders, unconnected people and the failed send aren't
  // produced by the backend yet (later milestones). They're shown with fixed sample content
  // for the Kids ministry demo persona, as agreed for the presentation.
  protected readonly showSamples = computed(() => this.session.ministry()?.ministry === 'Kids');
  protected readonly checkInAnswered = signal(false);
  protected readonly sendState = signal<'ready' | 'partial' | 'sent'>('ready');

  protected readonly needsYou = computed(
    () =>
      this.items().filter((i) => i.type !== 'load').length + (this.showSamples() && !this.checkInAnswered() ? 1 : 0),
  );
  protected readonly today = computed(() => longDate(churchToday(this.session.state()?.timezone ?? 'UTC')));
  protected readonly approvalCount = computed(
    () => this.memorySuggestions().length + this.rosterProposals().length + (this.showSamples() ? 1 : 0),
  );
  protected readonly monthDay = monthDay;

  constructor() {
    effect(() => {
      const churchId = this.session.churchId();
      const personId = this.session.personId();
      this.session.ministryId(); // reload when the ministry changes
      if (churchId && personId) this.load(churchId, personId);
    });
  }

  protected kind(item: BriefingItem): CardKind {
    return item.type as CardKind;
  }

  /** "Anna Parker is on Kids and Worship at the same time on Oct 11." */
  protected overlapHeadline(item: BriefingItem): string {
    const where = item.ministries.length > 1 ? item.ministries.join(' and ') : `${item.ministries[0]} twice`;
    return `${item.people[0]} is on ${where} at the same time on ${monthDay(item.on)}.`;
  }

  /** Split a check's sentence at its first comma: a short headline, then the details. */
  protected split(text: string): [string, string] {
    const at = text.indexOf(', ');
    if (at < 0) return [text.replace(/\.$/, ''), ''];
    const rest = text.slice(at + 2);
    return [text.slice(0, at), rest.charAt(0).toUpperCase() + rest.slice(1)];
  }

  protected remember(p: Proposal): void {
    this.decide(p, 'approve', 'Saved. Shepherd will use this in suggestions.');
  }

  protected notNow(p: Proposal): void {
    this.decide(p, 'reject', "Okay, Shepherd won't remember that.");
  }

  protected approveRoster(p: Proposal): void {
    this.decide(p, 'approve', 'Roster approved and recorded.');
  }

  protected copySample(text: string): void {
    void navigator.clipboard?.writeText(text).catch(() => undefined);
  }

  private decide(p: Proposal, action: 'approve' | 'reject', done: string): void {
    this.busy.set(p.id);
    this.queueMessage.set('');
    const call =
      action === 'approve'
        ? this.api.approve(this.session.churchId(), p.id, this.session.personId())
        : this.api.reject(this.session.churchId(), p.id, this.session.personId());
    call.subscribe({
      next: () => {
        this.busy.set(null);
        this.queueMessage.set(done);
        this.proposals.update((all) => all.filter((x) => x.id !== p.id));
      },
      error: (e) => {
        this.busy.set(null);
        this.queueMessage.set(e?.error?.detail ?? "That didn't work. Please try again.");
      },
    });
  }

  private load(churchId: string, personId: string): void {
    this.loading.set(true);
    this.error.set('');
    this.api.briefing(churchId, personId).subscribe({
      next: (b) => {
        this.briefing.set(b);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.error.set("Shepherd couldn't load your week. Is the server running?");
      },
    });
    this.api.pendingProposals(churchId).subscribe((p) => this.proposals.set(p));
  }
}
