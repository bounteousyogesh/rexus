/** Format an ISO timestamp for display in sync job UI. */
export function formatScheduleTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const normalized = iso.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(iso) ? iso : `${iso}Z`;
  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) return iso.slice(0, 16).replace('T', ' ');
  return parsed.toLocaleString(undefined, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}
