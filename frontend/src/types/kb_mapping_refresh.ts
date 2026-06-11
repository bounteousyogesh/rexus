export type KbArticleFilter = 'all' | 'synced' | 'not_synced';

export interface KbMappingRefreshIncident {
  incident_number: string;
  short_description: string;
  opened_at: string;
  cmdb_ci: string;
  category: string;
  has_kb_article: boolean | null;
}

export interface KbMappingRefreshGroup {
  month?: string;
  week?: string;
  day?: string;
  count: number;
  incidents: KbMappingRefreshIncident[];
}

export interface KbMappingRefreshPreview {
  filter: { has_kb_article: KbArticleFilter };
  total: number;
  by_month: KbMappingRefreshGroup[];
  by_week: KbMappingRefreshGroup[];
  by_day: KbMappingRefreshGroup[];
}

export interface KbMappingRefreshResult {
  incident: string;
  status: 'mapped' | 'no_kb' | 'not_found' | 'error';
  kb_from_sn?: number;
  kb_inserted?: number;
  error?: string;
}

export interface KbMappingRefreshSummary {
  candidates: number;
  with_kb: number;
  kb_rows_inserted: number;
  kb_rows_existing: number;
  no_kb: number;
  not_found: number;
  errors: number;
}

export interface KbMappingRefreshResponse {
  summary: KbMappingRefreshSummary;
  results: KbMappingRefreshResult[];
}
