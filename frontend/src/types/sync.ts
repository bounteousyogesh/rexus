export interface SyncStatus {
  database: {
    total_incidents: number;
    embedded: number;
    latest_incident_date: string | null;
  };
  servicenow: {
    closed_incidents: number | string;
  };
  catalog?: {
    path: string;
    available: boolean;
    date_min: string | null;
    date_max: string | null;
  };
  import_max_incidents?: number;
  refresh_max_incidents?: number;
}

export interface SyncIncident {
  incident_number: string;
  short_description: string;
  opened_at: string;
  cmdb_ci: string;
  category: string;
}

export interface SyncDeltaGroup {
  month?: string;
  week?: string;
  day?: string;
  count: number;
  incidents: SyncIncident[];
}

export interface SyncDelta {
  total_delta: number;
  total_discovered: number;
  already_in_db: number;
  source: string;
  message?: string | null;
  catalog_date_min?: string | null;
  catalog_date_max?: string | null;
  by_month: SyncDeltaGroup[];
  by_week: SyncDeltaGroup[];
  by_day: SyncDeltaGroup[];
}

export type SyncImportStatus = 'imported' | 'error' | 'skipped_not_closed' | 'not_found';

export interface SyncImportResult {
  incident: string;
  status: SyncImportStatus;
  error?: string;
  state?: string;
}

export interface SyncImportResponse {
  results: SyncImportResult[];
  imported: number;
  failed: number;
  skipped: number;
}
