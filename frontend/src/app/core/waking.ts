import { HttpInterceptorFn } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { finalize } from 'rxjs';

const SLOW_AFTER_MS = 3000;

/** True while a request has been waiting long enough to mean the server is waking from sleep. */
@Injectable({ providedIn: 'root' })
export class Waking {
  readonly slow = signal(false);
  private pending = 0;

  begin(): () => void {
    this.pending++;
    const timer = setTimeout(() => this.slow.set(true), SLOW_AFTER_MS);
    return () => {
      clearTimeout(timer);
      if (--this.pending === 0) this.slow.set(false);
    };
  }
}

/** Free hosting puts the API to sleep when idle; the first request can take about a minute. */
export const wakingInterceptor: HttpInterceptorFn = (req, next) => {
  const done = inject(Waking).begin();
  return next(req).pipe(finalize(done));
};
