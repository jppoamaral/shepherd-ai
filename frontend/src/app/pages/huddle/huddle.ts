import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../api/api.service';
import type { Huddle, HuddleSide } from '../../api/types';
import { Session } from '../../core/session';
import { initials } from '../../core/format';
import { Icon } from '../../ui/icon';

/** Conflict huddle: two leaders, one double booking, 15 minutes to talk. The volunteer isn't invited. */
@Component({
  selector: 'sh-huddle',
  imports: [RouterLink, FormsModule, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './huddle.css',
  templateUrl: './huddle.html',
})
export class HuddlePage {
  /** Route parameter (component input binding). */
  readonly findingId = input.required<string>();

  private readonly api = inject(ApiService);
  protected readonly session = inject(Session);

  protected readonly huddle = signal<Huddle | null>(null);
  protected readonly error = signal('');
  protected readonly working = signal(false);
  protected readonly picked = signal<string | null>(null);
  protected readonly decision = signal<string | null>(null);
  /** Shown after Undo, once the Resolve confirmation has gone. */
  protected readonly undone = signal('');
  protected note = '';

  protected readonly step = computed(() => {
    const h = this.huddle();
    if (!h) return 1;
    return h.status === 'resolved' ? 4 : h.status === 'scheduled' ? 3 : this.picked() ? 2 : 1;
  });
  protected readonly volunteer = computed(() => this.huddle()?.agenda.volunteer ?? '');
  protected readonly volunteerFirst = computed(() => this.volunteer().split(' ')[0]);
  protected readonly me = computed(() => this.huddle()?.leaders.find((l) => l.person_id === this.session.personId()));
  protected readonly other = computed(() => this.huddle()?.leaders.find((l) => l.person_id !== this.session.personId()));
  protected readonly when = computed(() => this.huddle()?.agenda.title.split(', ').slice(1).join(', ') ?? '');
  protected readonly options = computed(() => {
    const sides = this.huddle()?.agenda.sides ?? [];
    return [
      ...sides.map((s) => `${this.volunteerFirst()} serves in ${s.ministry}`),
      'Other',
    ];
  });
  /** After Resolve: the ministry whose roster didn't change (and whose leader wasn't told). */
  protected readonly untouched = computed(() => {
    const h = this.huddle();
    return h?.agenda.sides.find((s) => s.ministry_id !== h.replacement?.ministry_id)?.ministry ?? '';
  });
  protected readonly initials = initials;
  protected readonly first = (name: string) => name.split(' ')[0];

  constructor() {
    effect(() => {
      const id = this.findingId();
      if (id && this.session.churchId()) this.start(id);
    });
  }

  protected ministryOf(personId: string): string {
    const h = this.huddle();
    const leader = h?.leaders.find((l) => l.person_id === personId);
    return h?.agenda.sides.find((s) => s.leader === leader?.name)?.ministry ?? '';
  }

  /** Resolve shows only on a side whose roster this leader approves, while the conflict is open. */
  protected canResolve(side: HuddleSide): boolean {
    return !!side.replacement_person_id && this.huddle()?.status !== 'resolved' && this.approves(side.ministry_id);
  }

  protected approves(ministryId: string | null | undefined): boolean {
    return !!this.session.leader()?.ministries.some((m) => m.ministry_id === ministryId && m.can_approve);
  }

  protected resolveWith(side: HuddleSide): void {
    const h = this.huddle();
    if (!h || !side.ministry_id) return;
    this.undone.set('');
    this.run(this.api.acceptReplacement(this.session.churchId(), h.id, this.session.personId(), side.ministry_id));
  }

  protected undo(): void {
    const h = this.huddle();
    const r = h?.replacement;
    if (!h || !r) return;
    this.run(this.api.undoReplacement(this.session.churchId(), h.id, this.session.personId()), () =>
      this.undone.set(`${this.first(r.volunteer)} is back on ${r.ministry}. The double booking is open again.`),
    );
  }

  protected confirm(): void {
    const h = this.huddle();
    const slot = this.picked();
    if (!h || !slot) return;
    this.run(this.api.chooseSlot(this.session.churchId(), h.id, this.session.personId(), slot));
  }

  protected record(): void {
    const h = this.huddle();
    const choice = this.decision();
    if (!h || !choice) return;
    const outcome = this.note.trim() ? `${choice}. ${this.note.trim()}` : choice;
    this.run(this.api.resolveHuddle(this.session.churchId(), h.id, this.session.personId(), outcome));
  }

  private start(findingId: string): void {
    this.run(this.api.startHuddle(this.session.churchId(), findingId, this.session.personId()));
  }

  private run(call: ReturnType<ApiService['startHuddle']>, done?: () => void): void {
    this.working.set(true);
    this.error.set('');
    call.subscribe({
      next: (h) => {
        this.huddle.set(h);
        this.working.set(false);
        if (h.chosen_slot) this.picked.set(h.chosen_slot.id);
        done?.();
      },
      error: (e) => {
        this.working.set(false);
        this.error.set(e?.error?.detail ?? "Shepherd couldn't do that. Please try again.");
      },
    });
  }
}
