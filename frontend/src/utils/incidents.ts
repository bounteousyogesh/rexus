/** Tailwind classes for incident priority badges. */
export function priorityBadgeClass(priority?: string): string {
  if (!priority) return 'bg-slate-100 text-slate-500';
  if (priority.includes('1')) return 'bg-red-100 text-red-700';
  if (priority.includes('2')) return 'bg-orange-100 text-orange-700';
  if (priority.includes('3')) return 'bg-yellow-100 text-yellow-700';
  return 'bg-slate-100 text-slate-600';
}
