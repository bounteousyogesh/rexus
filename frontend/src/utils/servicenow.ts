const SERVICENOW_INSTANCE =
  (import.meta.env.VITE_SERVICENOW_INSTANCE as string | undefined)?.replace(/\/$/, '') ??
  'https://dtcprod.service-now.com';

function normalizeId(number: string): string {
  return number.trim().toUpperCase();
}

/** ServiceNow incident classic nav deep link. */
export function buildIncidentUrl(number: string): string {
  const id = normalizeId(number);
  if (!id) return '';
  return `${SERVICENOW_INSTANCE}/now/nav/ui/classic/params/target/incident.do%3Fsysparm_query%3Dnumber?sysparm_query=number=${encodeURIComponent(id)}`;
}

/** ServiceNow problem record deep link (problem.do?sysparm_query=number=…). */
export function buildProblemUrl(number: string): string {
  const id = normalizeId(number);
  if (!id) return '';
  return `${SERVICENOW_INSTANCE}/problem.do?sysparm_query=number=${encodeURIComponent(id)}`;
}

/** Inline KB reference in playbook text — same viewer as Knowledge Article section. */
export function buildKbInlineUrl(number: string): string {
  return buildKbArticleUrl(number);
}

/** ServiceNow KB article view URL (kb_view.do?sysparm_article=…). */
export function buildKbArticleUrl(number: string): string {
  const trimmed = number.trim();
  if (!trimmed) return '';
  return `${SERVICENOW_INSTANCE}/kb_view.do?sysparm_article=${encodeURIComponent(trimmed)}`;
}
