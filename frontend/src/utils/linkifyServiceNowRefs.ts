import {
  buildIncidentUrl,
  buildKbInlineUrl,
  buildProblemUrl,
} from './servicenow';

const SN_REF_PATTERN = /^(INC|PRB|KB)\d+$/i;

function buildUrlForRef(id: string): string {
  const normalized = id.trim().toUpperCase();
  if (normalized.startsWith('INC')) return buildIncidentUrl(normalized);
  if (normalized.startsWith('PRB')) return buildProblemUrl(normalized);
  if (normalized.startsWith('KB')) return buildKbInlineUrl(normalized);
  return '';
}

function toMarkdownLink(id: string): string {
  const normalized = id.trim().toUpperCase();
  const url = buildUrlForRef(normalized);
  return url ? `[${normalized}](${url})` : normalized;
}

const MARKDOWN_LINK_RE = /\[([^\]]+)\]\(([^)]+)\)/g;
const BRACKET_CITATION_RE = /\[((?:[A-Z]{3}\d+)(?:\s*,\s*[A-Z]{3}\d+)*)\]/gi;
const INC_RE = /\b(INC\d+)\b/gi;
const PRB_RE = /\b(PRB\d+)\b/gi;
const KB_RE = /\b(KB\d+)\b/gi;

function protectMarkdownLinks(text: string, store: string[]): string {
  return text.replace(MARKDOWN_LINK_RE, (match) => {
    store.push(match);
    return `\x00LINK${store.length - 1}\x00`;
  });
}

function restoreMarkdownLinks(text: string, store: string[]): string {
  return text.replace(/\x00LINK(\d+)\x00/g, (_, index) => store[Number(index)]);
}

/**
 * Convert INC/PRB/KB references in playbook markdown into ServiceNow links.
 * Existing markdown links are preserved unchanged.
 */
export function linkifyServiceNowRefs(markdown: string): string {
  if (!markdown) return markdown;

  const protectedLinks: string[] = [];
  let text = protectMarkdownLinks(markdown, protectedLinks);

  text = text.replace(BRACKET_CITATION_RE, (match, inner: string) => {
    const ids = inner.split(/\s*,\s*/).map((part) => part.trim()).filter(Boolean);
    if (!ids.length || !ids.every((id) => SN_REF_PATTERN.test(id))) {
      return match;
    }
    return `(${ids.map(toMarkdownLink).join(', ')})`;
  });

  text = protectMarkdownLinks(text, protectedLinks);

  text = text.replace(INC_RE, (match) => toMarkdownLink(match));
  text = text.replace(PRB_RE, (match) => toMarkdownLink(match));
  text = text.replace(KB_RE, (match) => toMarkdownLink(match));

  return restoreMarkdownLinks(text, protectedLinks);
}
