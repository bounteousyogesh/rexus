/** Parse API UTC ISO timestamp (naive values are treated as UTC). */
export function parseUtcIso(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const normalized = iso.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(iso) ? iso : `${iso}Z`;
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

/** Short timezone label for the user's locale (e.g. IST, GMT+5:30). */
export function localTimeZoneShortName(): string {
  const parts = new Intl.DateTimeFormat(undefined, { timeZoneName: 'short' }).formatToParts(new Date());
  return parts.find((part) => part.type === 'timeZoneName')?.value ?? 'local';
}

/** Format a UTC ISO timestamp for display in the user's local timezone. */
export function formatScheduleTime(iso: string | null | undefined): string {
  const parsed = parseUtcIso(iso);
  if (!parsed) return iso ? iso.slice(0, 16).replace('T', ' ') : '—';
  return parsed.toLocaleString(undefined, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'short',
  });
}

/** Convert API UTC ISO to value for `<input type="datetime-local">` (local wall time). */
export function toDatetimeLocalValue(iso: string | null | undefined): string {
  const parsed = parseUtcIso(iso);
  if (!parsed) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}T${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`;
}

/** Convert datetime-local value (local wall time) to UTC ISO string for the API. */
export function fromDatetimeLocalValue(local: string): string | null {
  if (!local) return null;
  const parsed = new Date(local);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString();
}

/** Validate manual From/To dates (max 7 inclusive calendar days). */
export function validateSyncDateRange(startDate: string, endDate: string): string | null {
  if (!startDate || !endDate) return 'Start and end dates are required';
  const start = new Date(`${startDate}T00:00:00`);
  const end = new Date(`${endDate}T00:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return 'Invalid date';
  if (end < start) return 'End date must be on or after start date';
  const days = Math.round((end.getTime() - start.getTime()) / (24 * 60 * 60 * 1000));
  if (days > 6) return 'Date range must be at most 7 days';
  return null;
}

export function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Current local datetime for `<input type="datetime-local">` default. */
export function nowDatetimeLocalValue(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

/** Local datetime at least `minutesAhead` from now (for schedule start min/default). */
export function futureDatetimeLocalValue(minutesAhead = 1): string {
  const d = new Date(Date.now() + minutesAhead * 60_000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Schedule start must be strictly in the future. */
export function validateFutureScheduleStart(local: string): string | null {
  if (!local) return 'Start time is required';
  const parsed = new Date(local);
  if (Number.isNaN(parsed.getTime())) return 'Invalid date and time';
  if (parsed.getTime() <= Date.now()) return 'Start time must be in the future';
  return null;
}
