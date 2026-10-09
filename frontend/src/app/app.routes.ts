import { inject } from '@angular/core';
import { CanActivateFn, Router, Routes } from '@angular/router';
import { Session } from './core/session';

/** Without a chosen leader (no auth in the demo), go to "who are you?". */
const needsLeader: CanActivateFn = () =>
  inject(Session).state() ? true : inject(Router).createUrlTree(['/pick']);

export const routes: Routes = [
  { path: 'pick', loadComponent: () => import('./pages/pick/pick').then((m) => m.PickPage), title: 'Shepherd' },
  // Demo of the volunteer side (stands in for Telegram): no leader, no sign-in.
  {
    path: 'demo/volunteers',
    loadComponent: () => import('./pages/demo/volunteers').then((m) => m.DemoVolunteersPage),
    title: 'Volunteer chat (demo) · Shepherd',
  },
  {
    path: 'demo/chat/:personId',
    loadComponent: () => import('./pages/demo/chat').then((m) => m.DemoChatPage),
    title: 'Volunteer chat (demo) · Shepherd',
  },
  {
    path: '',
    canActivate: [needsLeader],
    loadComponent: () => import('./shell/shell').then((m) => m.Shell),
    children: [
      { path: '', loadComponent: () => import('./pages/home/home').then((m) => m.HomePage), title: 'Home · Shepherd' },
      {
        path: 'ask',
        loadComponent: () => import('./pages/ask/ask').then((m) => m.AskPage),
        title: 'Ask Shepherd · Shepherd',
      },
      {
        path: 'rosters',
        loadComponent: () => import('./pages/rosters/rosters').then((m) => m.RostersPage),
        title: 'Rosters · Shepherd',
      },
      {
        path: 'memory',
        loadComponent: () => import('./pages/memory/memory').then((m) => m.MemoryPage),
        title: 'Memory · Shepherd',
      },
      {
        path: 'huddle/:findingId',
        loadComponent: () => import('./pages/huddle/huddle').then((m) => m.HuddlePage),
        title: 'Conflict huddle · Shepherd',
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
