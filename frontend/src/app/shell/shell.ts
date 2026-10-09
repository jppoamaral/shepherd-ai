import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { ApiService } from '../api/api.service';
import { Session } from '../core/session';
import { initials } from '../core/format';
import { Icon, IconName } from '../ui/icon';

interface NavItem {
  label: string;
  icon: IconName;
  link: string | null; // null = not designed yet
}

const NAV: NavItem[] = [
  { label: 'Home', icon: 'home', link: '/' },
  { label: 'Rosters', icon: 'calendar', link: '/rosters' },
  { label: 'People', icon: 'users', link: null },
  { label: 'Memory', icon: 'bookmark', link: '/memory' },
  { label: 'Settings', icon: 'gear', link: null },
];

/** Desktop: 240px sidebar. Phone: header with the ministry switcher and a bottom tab bar. */
@Component({
  selector: 'sh-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, NgTemplateOutlet, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './shell.css',
  template: `
    <div class="layout">
      <aside class="sh-side sidebar" aria-label="Shepherd">
        <div class="sh-wordmark brand"><span class="logo"><sh-icon name="logo" /></span>Shepherd</div>
        <ng-container [ngTemplateOutlet]="switcher" />
        <nav aria-label="Main" class="side-nav">
          @for (item of nav; track item.label) {
            @if (item.link) {
              <a class="sh-navitem" [routerLink]="item.link" routerLinkActive
                 #rla="routerLinkActive" [routerLinkActiveOptions]="{ exact: item.link === '/' }"
                 [attr.aria-current]="rla.isActive ? 'page' : null">
                <sh-icon [name]="item.icon" />{{ item.label }}
              </a>
            } @else {
              <span class="sh-navitem soon" aria-disabled="true" title="Not designed yet">
                <sh-icon [name]="item.icon" />{{ item.label }}<span class="sh-cap">Soon</span>
              </span>
            }
          }
        </nav>
        <div class="me">
          <div class="row">
            <span class="avatar">{{ initials() }}</span>
            <span class="me-text">
              <span class="me-name">{{ session.leader()?.name }}</span>
              <span class="sh-cap">{{ roleLine() }}</span>
            </span>
          </div>
          <button class="sh-btn sh-btn--quiet" type="button" (click)="switchLeader()">Switch leader</button>
          <p class="sh-cap">Shepherd suggests, you decide.</p>
        </div>
      </aside>

      <header class="mobile-head">
        <ng-container [ngTemplateOutlet]="switcher" />
        <button class="avatar avatar--big" type="button" [attr.aria-label]="session.leader()?.name + '. Switch leader'"
                (click)="switchLeader()">{{ initials() }}</button>
      </header>

      <main class="content" id="main">
        <router-outlet />
      </main>

      <nav class="sh-tabbar tabbar" aria-label="Main">
        @for (item of nav; track item.label) {
          @if (item.link) {
            <a class="sh-navitem" [routerLink]="item.link" routerLinkActive #rla="routerLinkActive"
               [routerLinkActiveOptions]="{ exact: item.link === '/' }"
               [attr.aria-current]="rla.isActive ? 'page' : null">
              <sh-icon [name]="item.icon" />{{ item.label }}
            </a>
          } @else {
            <span class="sh-navitem soon" aria-disabled="true" title="Not designed yet">
              <sh-icon [name]="item.icon" />{{ item.label }}
            </span>
          }
        }
      </nav>
    </div>

    <ng-template #switcher>
      <label class="sh-switcher switcher">
        <span class="visually-hidden">Switch ministry</span>
        <span class="switch-text">
          <span class="sh-cap">Ministry</span>
          <span>{{ session.ministry()?.ministry }}</span>
        </span>
        <sh-icon name="chevron" />
        <select [value]="session.ministryId()" (change)="switchMinistry($event)"
                [attr.aria-label]="'Switch ministry. Now showing ' + session.ministry()?.ministry">
          @for (m of session.leader()?.ministries ?? []; track m.ministry_id) {
            <option [value]="m.ministry_id">{{ m.ministry }}</option>
          }
        </select>
      </label>
    </ng-template>
  `,
})
export class Shell {
  protected readonly session = inject(Session);
  private readonly router = inject(Router);
  private readonly api = inject(ApiService);
  protected readonly nav = NAV;
  protected readonly initials = computed(() => initials(this.session.leader()?.name ?? ''));
  protected readonly roleLine = computed(() => {
    const m = this.session.ministry();
    if (!m) return '';
    const duty = m.can_schedule && m.can_approve ? 'coordinator' : m.can_schedule ? 'scheduler' : 'approver';
    return `${m.ministry} ${duty}`;
  });

  constructor() {
    // The demo data can be reset (new ids). If the remembered leader no longer exists,
    // go back to "who's leading today?" instead of showing errors; else refresh their ministries.
    const churchId = this.session.churchId();
    const personId = this.session.personId();
    this.api.leaders(churchId).subscribe({
      next: (leaders) => {
        const me = leaders.find((l) => l.person_id === personId);
        if (!me) return this.switchLeader();
        const state = this.session.state();
        if (state) this.session.signIn({ ...state, leader: me });
      },
      error: () => this.switchLeader(),
    });
  }

  protected switchMinistry(event: Event): void {
    this.session.switchMinistry((event.target as HTMLSelectElement).value);
  }

  protected switchLeader(): void {
    this.session.signOut();
    void this.router.navigate(['/pick']);
  }
}
