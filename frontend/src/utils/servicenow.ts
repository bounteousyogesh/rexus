const SERVICENOW_INSTANCE =
  (import.meta.env.VITE_SERVICENOW_INSTANCE as string | undefined)?.replace(/\/$/, '') ??
  'https://dtcprod.service-now.com';

/** ServiceNow KB article view URL (kb_view.do?sysparm_article=…). */
export function buildKbArticleUrl(number: string): string {
  const trimmed = number.trim();
  if (!trimmed) return '';
  return `${SERVICENOW_INSTANCE}/kb_view.do?sysparm_article=${encodeURIComponent(trimmed)}`;
}