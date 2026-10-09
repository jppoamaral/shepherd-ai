import { Injectable, computed, signal } from '@angular/core';
import type { Leader } from '../api/types';

export interface SessionState {
  churchId: string;
  churchName: string;
  timezone: string;
  leader: Leader;
  ministryId: string;
}

const KEY = 'shepherd.session';

/**
 * "Who am I" for the demo (no auth yet): the chosen church, leader and current ministry.
 * Kept in localStorage as a per-viewer convenience; the app works without it.
 */
@Injectable({ providedIn: 'root' })
export class Session {
  readonly state = signal<SessionState | null>(load());

  readonly churchId = computed(() => this.state()?.churchId ?? '');
  readonly personId = computed(() => this.state()?.leader.person_id ?? '');
  readonly leader = computed(() => this.state()?.leader ?? null);
  readonly ministryId = computed(() => this.state()?.ministryId ?? '');
  readonly ministry = computed(() => {
    const s = this.state();
    return s?.leader.ministries.find((m) => m.ministry_id === s.ministryId) ?? null;
  });
  readonly firstName = computed(() => this.leader()?.name.split(' ')[0] ?? '');

  signIn(state: SessionState): void {
    this.set(state);
  }

  switchMinistry(ministryId: string): void {
    const s = this.state();
    if (s) this.set({ ...s, ministryId });
  }

  signOut(): void {
    this.state.set(null);
    try {
      localStorage.removeItem(KEY);
    } catch {
      /* storage unavailable: nothing to clear */
    }
  }

  private set(state: SessionState): void {
    this.state.set(state);
    try {
      localStorage.setItem(KEY, JSON.stringify(state));
    } catch {
      /* storage unavailable: the session just won't survive a reload */
    }
  }
}

function load(): SessionState | null {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as SessionState) : null;
  } catch {
    return null;
  }
}
