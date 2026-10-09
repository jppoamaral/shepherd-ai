import { ChangeDetectionStrategy, Component, computed, effect, inject, signal } from '@angular/core';
import { ApiService } from '../../api/api.service';
import type { Roster, Suggestion, SuggestionLine } from '../../api/types';
import { Session } from '../../core/session';
import { churchToday, dayTime, monthDay } from '../../core/format';
import { ExperienceBadge } from '../../ui/experience-badge';
import { Icon } from '../../ui/icon';

interface EditLine {
  line: SuggestionLine;
  /** The person chosen in the edit view (starts as Shepherd's suggestion). */
  personId: string | null;
}

const FLAG_TEXT: Record<string, string> = {
  double_booked: 'Double-booked: also serving at the same time in another ministry.',
  over_load: 'Above the usual load this week.',
  above_usual: 'Serving more than usual this week.',
};

/** Rosters: Shepherd's suggestion (choose, edit, approve) and the roster as it stands. */
@Component({
  selector: 'sh-rosters',
  imports: [Icon, ExperienceBadge],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './rosters.css',
  templateUrl: './rosters.html',
})
export class RostersPage {
  private readonly api = inject(ApiService);
  protected readonly session = inject(Session);

  protected readonly suggestion = signal<Suggestion | null>(null);
  protected readonly current = signal<Roster | null>(null);
  protected readonly editing = signal(false);
  protected readonly edits = signal<EditLine[]>([]);
  protected readonly working = signal(false);
  protected readonly approved = signal('');
  protected readonly error = signal('');

  protected readonly monthDay = monthDay;
  protected readonly dayTime = dayTime;
  protected readonly flagText = FLAG_TEXT;

  protected readonly title = computed(() => {
    const s = this.suggestion();
    if (!s) return 'Rosters';
    const month = new Date(`${s.start}T12:00:00`).toLocaleString('en-US', { month: 'long' });
    return `${month} rosters`;
  });
  protected readonly toApprove = computed(() =>
    this.edits().filter((e) => e.personId !== null),
  );

  constructor() {
    effect(() => {
      if (this.session.churchId() && this.session.ministryId()) this.load();
    });
  }

  protected choose(): void {
    const s = this.suggestion();
    if (!s) return;
    this.edits.set(s.lines.map((line) => ({ line, personId: line.person_id ?? null })));
    this.editing.set(true);
    this.approved.set('');
  }

  protected options(e: EditLine): { id: string; name: string }[] {
    const people = [
      ...(e.line.person_id && e.line.name ? [{ id: e.line.person_id, name: e.line.name }] : []),
      ...e.line.alternatives.map((a) => ({ id: a.person_id, name: a.name })),
    ];
    return people;
  }

  protected nameOf(e: EditLine): string | null {
    return this.options(e).find((o) => o.id === e.personId)?.name ?? null;
  }

  protected swap(index: number, personId: string): void {
    this.edits.update((all) => all.map((e, i) => (i === index ? { ...e, personId: personId || null } : e)));
  }

  protected approve(): void {
    const chosen = this.toApprove().map((e) => ({
      gathering_id: e.line.gathering_id,
      role_id: e.line.role_id,
      person_id: e.personId as string,
      reason: e.personId === e.line.person_id ? e.line.reason : 'Changed by you.',
    }));
    if (!chosen.length) return;
    this.working.set(true);
    this.error.set('');
    this.api
      .approveSuggestion(this.session.churchId(), this.session.ministryId(), this.session.personId(), chosen)
      .subscribe({
        next: () => {
          this.working.set(false);
          this.editing.set(false);
          this.approved.set(`Roster approved: ${chosen.length} ${chosen.length === 1 ? 'place' : 'places'} recorded.`);
          this.load();
        },
        error: (e) => {
          this.working.set(false);
          this.error.set(e?.error?.detail ?? "That didn't work. Please try again.");
        },
      });
  }

  private load(): void {
    const s = this.session;
    this.suggestion.set(null);
    this.api.suggestion(s.churchId(), s.ministryId()).subscribe({
      next: (r) => this.suggestion.set(r),
      error: () => this.error.set("Shepherd couldn't draft a roster. Is the server running?"),
    });
    const today = churchToday(s.state()?.timezone ?? 'UTC');
    const end = new Date(`${today}T12:00:00Z`);
    end.setUTCDate(end.getUTCDate() + 7);
    this.api.roster(s.churchId(), s.ministryId(), today, end.toISOString().slice(0, 10)).subscribe((r) => this.current.set(r));
  }
}
