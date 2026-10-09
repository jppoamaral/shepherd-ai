import { ChangeDetectionStrategy, Component, DestroyRef, computed, effect, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../api/api.service';
import type { ChatThread } from '../../api/types';
import { Icon } from '../../ui/icon';

/** One line in the phone: Shepherd's (from the server) or hers (kept in this browser). */
interface Line {
  key: string;
  from: 'shepherd' | 'her';
  body: string;
  at: string;
  buttons: string[];
}

interface Mine {
  body: string;
  at: string;
}

const POLL_MS = 2000;

/**
 * Volunteer chat simulator (demo): stands in for Telegram. Volunteers never use the app.
 * Shepherd's side comes from the server (only approved messages and the bot's replies);
 * her own messages stay in this browser, as they would stay in Telegram. Tapping a button
 * sends its text, exactly as typing it would.
 */
@Component({
  selector: 'sh-demo-chat',
  imports: [FormsModule, RouterLink, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './chat.css',
  templateUrl: './chat.html',
  host: { '[class.embedded]': 'embed()' },
})
export class DemoChatPage {
  /** Route parameter and query parameters (component input binding). */
  readonly personId = input.required<string>();
  readonly church = input<string>('');
  readonly embed = input<string | undefined>(undefined);

  private readonly api = inject(ApiService);

  protected readonly thread = signal<ChatThread | null>(null);
  protected readonly mine = signal<Mine[]>([]);
  protected readonly failed = signal(false);
  protected readonly sending = signal(false);
  protected draft = '';

  protected readonly first = computed(() => this.thread()?.name.split(' ')[0] ?? '');
  protected readonly lines = computed<Line[]>(() => {
    const shepherd: Line[] = (this.thread()?.messages ?? []).map((m) => ({
      key: m.id,
      from: 'shepherd',
      body: m.body,
      at: m.at,
      buttons: m.buttons,
    }));
    const hers: Line[] = this.mine().map((m, i) => ({ key: `me-${i}`, from: 'her', body: m.body, at: m.at, buttons: [] }));
    return [...shepherd, ...hers].sort((a, b) => a.at.localeCompare(b.at));
  });
  /** Buttons show only under Shepherd's latest message, until she answers. */
  protected readonly buttonsFor = computed(() => {
    const all = this.lines();
    const last = all[all.length - 1];
    return last && last.from === 'shepherd' && last.buttons.length ? last.key : null;
  });

  constructor() {
    effect(() => {
      const personId = this.personId();
      this.mine.set(load(personId));
      this.refresh();
    });
    const timer = setInterval(() => this.refresh(), POLL_MS);
    inject(DestroyRef).onDestroy(() => clearInterval(timer));
  }

  protected submit(): void {
    const text = this.draft.trim();
    if (!text) return;
    this.draft = '';
    this.send(text);
  }

  protected send(text: string): void {
    if (this.sending() || !this.church()) return;
    const mine = [...this.mine(), { body: text, at: new Date().toISOString() }];
    this.mine.set(mine);
    save(this.personId(), mine);
    this.sending.set(true);
    this.api.say(this.church(), this.personId(), text).subscribe({
      next: () => {
        this.sending.set(false);
        this.refresh();
      },
      error: () => {
        this.sending.set(false);
        this.failed.set(true);
      },
    });
  }

  protected day(at: string): string {
    const d = new Date(at);
    const today = new Date();
    if (d.toDateString() === today.toDateString()) return 'Today';
    return d.toLocaleDateString([], { weekday: 'long' });
  }

  protected time(at: string): string {
    return new Date(at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  }

  protected clear(): void {
    this.mine.set([]);
    save(this.personId(), []);
  }

  private refresh(): void {
    if (!this.church()) return;
    this.api.chat(this.church(), this.personId()).subscribe({
      next: (t) => {
        this.failed.set(false);
        const before = this.thread()?.messages.length ?? 0;
        this.thread.set(t);
        if (t.messages.length !== before) setTimeout(() => scrollDown());
      },
      error: () => this.failed.set(true),
    });
  }
}

function load(personId: string): Mine[] {
  try {
    return JSON.parse(localStorage.getItem(`shepherd.chat.${personId}`) ?? '[]') as Mine[];
  } catch {
    return [];
  }
}

function save(personId: string, mine: Mine[]): void {
  try {
    localStorage.setItem(`shepherd.chat.${personId}`, JSON.stringify(mine));
  } catch {
    /* storage unavailable: her side of the chat just won't survive a reload */
  }
  setTimeout(() => scrollDown());
}

function scrollDown(): void {
  const log = document.querySelector('.phone .log');
  if (log) log.scrollTop = log.scrollHeight;
}
