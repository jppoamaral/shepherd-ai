import { ChangeDetectionStrategy, Component, DestroyRef, computed, effect, inject, signal } from '@angular/core';
import { ApiService } from '../../api/api.service';
import type { Briefing, BriefingItem, GapFill, Leader, Notice, Proposal } from '../../api/types';
import { Session } from '../../core/session';
import { churchToday, longDate } from '../../core/format';
import { Icon } from '../../ui/icon';
import { FindingCard } from './finding-card';
import { NoticeCard, noticeNeedsLeader } from './notice-card';
import { ProposalCard, reminderCount } from './proposal-card';

/** Home: the weekly briefing for the current ministry, and what's waiting for approval. */
@Component({
  selector: 'sh-home',
  imports: [Icon, FindingCard, NoticeCard, ProposalCard],
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
  protected readonly notices = signal<Notice[]>([]);
  protected readonly leaders = signal<Leader[]>([]);
  /** Only a ministry's approvers can approve its rosters and send its reminders. */
  protected readonly canApprove = computed(() => !!this.session.ministry()?.can_approve);
  protected readonly approverNames = computed(() => {
    const ministryId = this.session.ministryId();
    const names = this.leaders()
      .filter((l) => l.ministries.some((m) => m.ministry_id === ministryId && m.can_approve))
      .map((l) => l.name);
    return names.length > 1 ? `${names.slice(0, -1).join(', ')} or ${names[names.length - 1]}` : (names[0] ?? 'an approver');
  });
  /** Which reminders card is expanded to review every message. */
  protected readonly reviewing = signal<string | null>(null);

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
  protected readonly reminderProposals = computed(() =>
    this.proposals().filter((p) => p.type === 'reminders' && p.payload['ministry_id'] === this.session.ministryId()),
  );
  /** Notes from volunteers' chats for the ministry being viewed. */
  protected readonly myNotices = computed(() =>
    this.notices().filter((n) => n.ministry_id === this.session.ministryId()),
  );

  protected readonly needsYou = computed(
    () =>
      this.items().filter((i) => i.type !== 'load').length +
      this.myNotices().filter(noticeNeedsLeader).length,
  );
  protected readonly today = computed(() => longDate(churchToday(this.session.state()?.timezone ?? 'UTC')));
  protected readonly approvalCount = computed(
    () => this.memorySuggestions().length + this.rosterProposals().length + this.reminderProposals().length,
  );

  constructor() {
    effect(() => {
      const churchId = this.session.churchId();
      const personId = this.session.personId();
      this.session.ministryId(); // reload when the ministry changes
      if (churchId && personId) this.load(churchId, personId);
    });
    // Volunteers answer in their chat while the leader watches: pick up new notices.
    const timer = setInterval(() => this.checkNotices(), 3000);
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
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

  protected sendReminders(p: Proposal): void {
    const n = reminderCount(p);
    this.decide(p, 'approve', `Sent ${n} ${n === 1 ? 'reminder' : 'reminders'}, each 1:1.`);
  }

  /** Fill an open slot with the person Shepherd found free: recorded through the approval queue. */
  protected fill(item: BriefingItem, fill: GapFill): void {
    this.busy.set(item.finding_id);
    this.queueMessage.set('');
    this.api
      .approveSuggestion(this.session.churchId(), fill.ministry_id, this.session.personId(), [
        { gathering_id: fill.gathering_id, role_id: fill.role_id, person_id: fill.person_id, reason: 'Filled an open slot.' },
      ])
      .subscribe({
        next: () => {
          this.busy.set(null);
          this.queueMessage.set(`${fill.name} is on the roster as ${fill.role}.`);
          this.load(this.session.churchId(), this.session.personId());
          this.checkNotices(); // a decline notice about this place is now covered
        },
        error: (e) => {
          this.busy.set(null);
          this.queueMessage.set(e?.error?.detail ?? "That didn't work. Please try again.");
        },
      });
  }

  /** "Still on the team?": yes settles it, later asks again in four weeks. The team never changes. */
  protected answerCheckIn(item: BriefingItem, answer: 'still_here' | 'later'): void {
    this.busy.set(item.finding_id);
    this.queueMessage.set('');
    this.api.answerCheckIn(this.session.churchId(), item.finding_id, this.session.personId(), answer).subscribe({
      next: () => {
        this.busy.set(null);
        this.briefing.update((b) => b && { ...b, items: b.items.filter((i) => i.finding_id !== item.finding_id) });
      },
      error: (e) => {
        this.busy.set(null);
        this.queueMessage.set(e?.error?.detail ?? "That didn't work. Please try again.");
      },
    });
  }

  /** Someone said yes when asked: put them in (a swap if it was someone's place), through
   * the approval queue. */
  protected putIn(n: Notice): void {
    this.busy.set(n.id);
    this.queueMessage.set('');
    this.api
      .putIn(this.session.churchId(), n.id, this.session.personId())
      .subscribe({
        next: (out) => {
          this.busy.set(null);
          this.queueMessage.set(out.text);
          this.load(this.session.churchId(), this.session.personId());
          this.checkNotices();
        },
        error: (e) => {
          this.busy.set(null);
          this.queueMessage.set(e?.error?.detail ?? "That didn't work. Please try again.");
        },
      });
  }

  /** Dismissing deletes the notice, including anything personal the volunteer passed on. */
  protected dismiss(n: Notice): void {
    this.api.dismissNotice(this.session.churchId(), n.id, this.session.personId()).subscribe(() =>
      this.notices.update((all) => all.filter((x) => x.id !== n.id)),
    );
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
    this.api.notices(churchId, personId).subscribe((n) => this.notices.set(n));
    this.api.leaders(churchId).subscribe((l) => this.leaders.set(l));
  }

  private checkNotices(): void {
    const churchId = this.session.churchId();
    const personId = this.session.personId();
    if (!churchId || !personId) return;
    this.api.notices(churchId, personId).subscribe((n) => {
      const known = new Set(this.notices().map((x) => x.id));
      this.notices.set(n);
      // Something new from a volunteer: the record may have changed too (a decline opens a slot).
      if (n.some((x) => !known.has(x.id))) this.load(churchId, personId);
    });
  }
}
