import { ChangeDetectionStrategy, Component, computed, effect, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../api/api.service';
import type { Huddle } from '../../api/types';
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
  protected readonly initials = initials;

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

  private run(call: ReturnType<ApiService['startHuddle']>): void {
    this.working.set(true);
    this.error.set('');
    call.subscribe({
      next: (h) => {
        this.huddle.set(h);
        this.working.set(false);
        if (h.chosen_slot) this.picked.set(h.chosen_slot.id);
      },
      error: (e) => {
        this.working.set(false);
        this.error.set(e?.error?.detail ?? "Shepherd couldn't do that. Please try again.");
      },
    });
  }
}
