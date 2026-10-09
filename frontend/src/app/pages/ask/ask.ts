import { ChangeDetectionStrategy, Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../api/api.service';
import type { AskAction, AskAnswer, AskDraft, AskIn, AskStart } from '../../api/types';
import { Session } from '../../core/session';
import { initials } from '../../core/format';
import { Icon } from '../../ui/icon';

type Question = Omit<AskIn, 'person_id'>;

interface Turn {
  id: number;
  /** What the leader asked, as shown in their bubble. */
  text: string;
  question: Question;
  state: 'thinking' | 'done' | 'failed';
  answer?: AskAnswer;
}

/**
 * Ask Shepherd: questions in the leader's own words, answered from the record.
 * The conversation lives only on this page (nothing is stored). Drafts are for the
 * leader to edit, then copy or Send: tapping Send is their approval, and Shepherd sends
 * each message 1:1 through the church's channel.
 */
@Component({
  selector: 'sh-ask',
  imports: [FormsModule, NgTemplateOutlet, RouterLink, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './ask.css',
  templateUrl: './ask.html',
})
export class AskPage {
  private readonly api = inject(ApiService);
  protected readonly session = inject(Session);

  protected readonly start = signal<AskStart | null>(null);
  protected readonly startFailed = signal(false);
  protected readonly turns = signal<Turn[]>([]);
  protected draft = '';
  /** Draft bodies the leader edited, keyed by turn and draft index. */
  protected readonly edited = signal<Record<string, string>>({});
  protected readonly editing = signal<string | null>(null);
  protected readonly copied = signal<string | null>(null);
  /** Drafts already sent, by draft key; the turn being sent; each turn's result line. */
  protected readonly sent = signal<Record<string, true>>({});
  protected readonly sendingTurn = signal<number | null>(null);
  protected readonly sendResult = signal<Record<number, string>>({});

  protected readonly thinking = computed(() => this.turns().some((t) => t.state === 'thinking'));
  protected readonly lookedAt = computed(() => {
    const done = this.turns().filter((t) => t.answer);
    return done.length ? done[done.length - 1].answer!.looked_at : [];
  });
  protected readonly ministry = computed(() => this.session.ministry()?.ministry ?? '');
  protected readonly initials = initials;
  protected readonly experience: Record<string, string> = { new: 'New', experienced: 'Experienced', veteran: 'Veteran' };
  private nextId = 1;

  constructor() {
    // A new ministry is a new conversation.
    effect(() => {
      const churchId = this.session.churchId();
      const ministryId = this.session.ministryId();
      if (!churchId || !ministryId) return;
      untracked(() => {
        this.turns.set([]);
        this.edited.set({});
        this.loadStart();
      });
    });
  }

  protected submit(): void {
    const text = this.draft.trim();
    if (!text || this.thinking()) return;
    this.draft = '';
    this.send(text, { question: text });
  }

  protected tap(action: AskAction): void {
    if (this.thinking() || action.kind !== 'ask') return;
    this.send(action.label, {
      intent: action.intent,
      about_person_id: action.about_person_id,
      on: action.on,
      role_id: action.role_id,
    });
  }

  protected retry(turn: Turn): void {
    if (this.thinking()) return;
    this.update(turn.id, { state: 'thinking' });
    this.call(turn.id, turn.question);
  }

  protected copy(text: string, key: string): void {
    void navigator.clipboard
      ?.writeText(text)
      .then(() => this.copied.set(key))
      .catch(() => undefined);
  }

  protected draftKey(turn: Turn, index: number): string {
    return `${turn.id}:${index}`;
  }

  protected draftBody(turn: Turn, index: number): string {
    return this.edited()[this.draftKey(turn, index)] ?? turn.answer?.drafts[index]?.body ?? '';
  }

  protected setDraftBody(key: string, body: string): void {
    this.edited.update((all) => ({ ...all, [key]: body }));
  }

  /** Drafts in this answer Shepherd can still send (connected, not sent yet). */
  protected sendable(turn: Turn): number[] {
    return (turn.answer?.drafts ?? [])
      .map((d, i) => (d.can_send && !this.sent()[this.draftKey(turn, i)] ? i : -1))
      .filter((i) => i >= 0);
  }

  /** Send these drafts as the leader edited them. The tap is the approval. */
  protected sendDrafts(turn: Turn, indexes: number[]): void {
    const drafts = turn.answer?.drafts ?? [];
    if (!indexes.length || this.sendingTurn() !== null) return;
    const s = this.session;
    const chosen: AskDraft[] = indexes.map((i) => ({ ...drafts[i], body: this.draftBody(turn, i) }));
    this.editing.set(null);
    this.sendingTurn.set(turn.id);
    this.api.sendDrafts(s.churchId(), s.ministryId(), s.personId(), chosen).subscribe({
      next: (out) => {
        this.sendingTurn.set(null);
        const sentTo = new Set(out.sent);
        this.sent.update((all) => {
          const next = { ...all };
          indexes.forEach((i) => {
            if (sentTo.has(drafts[i].to_person_id)) next[this.draftKey(turn, i)] = true;
          });
          return next;
        });
        this.sendResult.update((all) => ({ ...all, [turn.id]: out.text }));
      },
      error: (e) => {
        this.sendingTurn.set(null);
        this.sendResult.update((all) => ({ ...all, [turn.id]: e?.error?.detail ?? "That didn't send. Please try again." }));
      },
    });
  }

  protected first(name: string): string {
    return name.split(' ')[0];
  }

  private send(text: string, question: Question): void {
    const id = this.nextId++;
    this.copied.set(null);
    this.turns.update((all) => [...all, { id, text, question, state: 'thinking' }]);
    this.scrollTo(id);
    this.call(id, question);
  }

  private call(id: number, question: Question): void {
    const s = this.session;
    this.api.ask(s.churchId(), s.ministryId(), { ...question, person_id: s.personId() }).subscribe({
      next: (answer) => {
        this.update(id, { state: 'done', answer });
        this.scrollTo(id);
      },
      error: () => this.update(id, { state: 'failed' }),
    });
  }

  private update(id: number, change: Partial<Turn>): void {
    this.turns.update((all) => all.map((t) => (t.id === id ? { ...t, ...change } : t)));
  }

  private loadStart(): void {
    const s = this.session;
    this.start.set(null);
    this.startFailed.set(false);
    this.api.askStart(s.churchId(), s.ministryId(), s.personId()).subscribe({
      next: (start) => this.start.set(start),
      error: () => this.startFailed.set(true),
    });
  }

  private scrollTo(id: number): void {
    setTimeout(() => {
      const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
      document.getElementById(`turn-${id}`)?.scrollIntoView({ block: 'end', behavior: reduce ? 'auto' : 'smooth' });
    });
  }
}
