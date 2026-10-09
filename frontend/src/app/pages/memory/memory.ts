import { ChangeDetectionStrategy, Component, computed, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Observable } from 'rxjs';
import { ApiService } from '../../api/api.service';
import type { Memory, MemoryItem, MemoryPending } from '../../api/types';
import { Session } from '../../core/session';
import { Icon } from '../../ui/icon';

const GROUPS: { kind: MemoryItem['kind']; title: string }[] = [
  { kind: 'habit', title: 'Habits' },
  { kind: 'growth', title: 'Growth notes' },
  { kind: 'preference', title: 'Volunteer preferences' },
  { kind: 'rule', title: 'Rules of thumb' },
];

/** What Shepherd remembers for this ministry. Saved only after the leader says yes. */
@Component({
  selector: 'sh-memory',
  imports: [FormsModule, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './memory.css',
  template: `
    <section class="page-head">
      <h1 class="t-h1">What Shepherd remembers for {{ session.ministry()?.ministry }}</h1>
      <p class="sh-muted">Only you and your ministry's leaders see this. Delete anything, any time.</p>
    </section>

    @if (message()) {
      <p class="sh-notice sh-notice--info" role="status"><sh-icon name="check" />{{ message() }}</p>
    }
    @if (error()) {
      <div class="sh-notice sh-notice--error" role="alert"><sh-icon name="alert" /><span>{{ error() }}</span></div>
    }

    @for (p of memory()?.pending ?? []; track p.proposal_id) {
      <article class="sh-card sh-card--suggest">
        <div class="sh-sugg-label"><span class="sh-spark"><sh-icon name="spark" /></span>Memory suggestion</div>
        <p>{{ p.text }} Remember this?</p>
        <div class="sh-actions">
          <button type="button" class="sh-btn sh-btn--primary" [disabled]="busy()" (click)="decide(p, true)">Remember</button>
          <button type="button" class="sh-btn sh-btn--quiet" [disabled]="busy()" (click)="decide(p, false)">Not now</button>
        </div>
        <div class="sh-note"><sh-icon name="lock" />Shepherd won't use this until you say yes.</div>
      </article>
    }

    @if (!memory()) {
      <div class="sh-card" role="status" aria-label="Loading memory">
        <div class="sh-skel"></div><div class="sh-skel"></div><div class="sh-skel short"></div>
      </div>
    } @else {
      <div class="sh-card">
        @for (group of groups(); track group.kind) {
          <h2 class="sh-group">{{ group.title }}</h2>
          @for (item of group.items; track item.id) {
            <div class="sh-mem">
              <div>
                <div class="sh-mem-text">{{ item.text }}</div>
                <div class="sh-mem-meta">
                  @if (item.proposed_from === 'volunteer') {
                    <span class="sh-tag sh-tag--soft"><sh-icon name="users" />Told by {{ firstName(item.about) }}</span>
                  } @else {
                    <span class="sh-cap">{{ item.proposed_from === 'leader_edit' ? 'From your roster edits' : 'Your note' }}</span>
                  }
                  <span class="sh-cap">Confirmed by {{ item.confirmed_by }}</span>
                </div>
              </div>
              <button type="button" class="sh-iconbtn" [attr.aria-label]="'Delete: ' + item.text" [disabled]="busy()"
                      (click)="remove(item)"><sh-icon name="trash" /></button>
            </div>
          }
        } @empty {
          <div class="sh-state">
            <h3>Nothing remembered yet</h3>
            <p>When Shepherd notices a habit, it will ask before remembering it.</p>
          </div>
        }
        <div class="sh-note"><sh-icon name="lock" />Shepherd never stores health, family or personal reasons.</div>
      </div>

      <form class="sh-card" (ngSubmit)="addNote()">
        <h2 class="sh-group">Tell Shepherd something to remember</h2>
        <label class="stack">
          <span class="sh-muted">For example: "Keep new helpers beside a veteran for their first month."</span>
          <textarea name="note" rows="2" maxlength="500" [(ngModel)]="note" aria-label="Something to remember"></textarea>
        </label>
        <button type="submit" class="sh-btn sh-btn--secondary" [disabled]="!note.trim() || busy()">Suggest it</button>
        <p class="sh-cap">It shows up above as a suggestion. Nothing is saved until you say yes.</p>
      </form>
    }
  `,
})
export class MemoryPage {
  private readonly api = inject(ApiService);
  protected readonly session = inject(Session);

  protected readonly memory = signal<Memory | null>(null);
  protected readonly busy = signal(false);
  protected readonly message = signal('');
  protected readonly error = signal('');
  protected note = '';

  protected readonly groups = computed(() =>
    GROUPS.map((g) => ({ ...g, items: (this.memory()?.items ?? []).filter((i) => i.kind === g.kind) })).filter(
      (g) => g.items.length > 0,
    ),
  );

  constructor() {
    effect(() => {
      const churchId = this.session.churchId();
      const ministryId = this.session.ministryId();
      if (churchId && ministryId) this.load();
    });
  }

  protected firstName(name: string | null | undefined): string {
    return (name ?? 'the volunteer').split(' ')[0];
  }

  protected decide(p: MemoryPending, remember: boolean): void {
    const s = this.session;
    const call = remember
      ? this.api.approve(s.churchId(), p.proposal_id, s.personId())
      : this.api.reject(s.churchId(), p.proposal_id, s.personId());
    this.act(call, remember ? 'Saved. Shepherd will use this in suggestions.' : "Okay, Shepherd won't remember that.");
  }

  protected remove(item: MemoryItem): void {
    const s = this.session;
    this.act(this.api.deleteMemory(s.churchId(), s.ministryId(), item.id, s.personId()), 'Deleted. Shepherd stopped using it.');
  }

  protected addNote(): void {
    const s = this.session;
    const text = this.note.trim();
    if (!text) return;
    this.act(this.api.noteMemory(s.churchId(), s.ministryId(), s.personId(), text), 'Added as a suggestion above.', () => {
      this.note = '';
    });
  }

  private act(call: Observable<unknown>, done: string, after?: () => void): void {
    this.busy.set(true);
    this.message.set('');
    this.error.set('');
    call.subscribe({
      next: () => {
        this.busy.set(false);
        this.message.set(done);
        after?.();
        this.load();
      },
      error: (e) => {
        this.busy.set(false);
        this.error.set(e?.error?.detail ?? "That didn't work. Please try again.");
      },
    });
  }

  private load(): void {
    this.api.memory(this.session.churchId(), this.session.ministryId()).subscribe({
      next: (m) => this.memory.set(m),
      error: () => this.error.set("Shepherd couldn't load memory. Is the server running?"),
    });
  }
}
