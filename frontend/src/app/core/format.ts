/**
 * Date formatting in the church's own time.
 *
 * The API returns local ISO strings with their offset (e.g. 2026-10-11T09:30:00-05:00).
 * We read the wall-clock parts straight from the string, so the browser's time zone
 * never shifts a 9:30 service.
 */
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const LONG_DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

interface Parts {
  y: number;
  m: number;
  d: number;
  h: number;
  min: number;
}

export function parts(iso: string): Parts {
  const [date, time = '00:00'] = iso.split('T');
  const [y, m, d] = date.split('-').map(Number);
  const [h, min] = time.split(':').map(Number);
  return { y, m, d, h, min };
}

function weekday(p: Parts): number {
  return new Date(Date.UTC(p.y, p.m - 1, p.d)).getUTCDay();
}

/** "9:30 AM" */
export function time(iso: string): string {
  const p = parts(iso);
  const hour = p.h % 12 || 12;
  return `${hour}:${String(p.min).padStart(2, '0')} ${p.h < 12 ? 'AM' : 'PM'}`;
}

/** "Oct 11" */
export function monthDay(iso: string): string {
  const p = parts(iso);
  return `${MONTHS[p.m - 1]} ${p.d}`;
}

/** "Sun 9:30" (for the roster row's small line) */
export function dayTime(iso: string): string {
  const p = parts(iso);
  return `${DAYS[weekday(p)]} ${p.h % 12 || 12}:${String(p.min).padStart(2, '0')}`;
}

/** "Thursday, Oct 8" */
export function longDate(isoDate: string): string {
  const p = parts(isoDate);
  return `${LONG_DAYS[weekday(p)]}, ${MONTHS[p.m - 1]} ${p.d}`;
}

/** Today's date in the church's time zone, as YYYY-MM-DD. */
export function churchToday(timezone: string): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: timezone }).format(new Date());
}

export function initials(name: string): string {
  return name
    .split(' ')
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
}
