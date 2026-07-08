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
  state?: string;
}

export interface NewIncident {
  incident_number: string;
  sys_id?: string;
  short_description: string;
  opened_at: string;
  cmdb_ci: string;
  category: string;
  state?: string;
  priority?: string;
  assignment_group?: string;
  assigned_to?: string;
  opened_by?: string;
}

export interface NewIncidentsPreview {
  sync_date: string;
  total: number;
  incidents: NewIncident[];
  db_count: number;
  last_synced_at: string | null;
}

export interface NewIncidentsRunResponse {
  sync_date: string;
  inserted: number;
  updated: number;
  errors: number;
  total: number;
  comments_posted: number;
  comments_failed: number;
  db_count: number;
  last_synced_at: string | null;
}

export interface NewIncidentSyncConfig {
  job_name: string;
  enabled: boolean;
  interval_hours: number;
  last_run_at: string | null;
  last_status: string | null;
  last_result: NewIncidentSyncResult | null;
  next_run_at: string | null;
  updated_at: string | null;
}

export interface NewIncidentSyncConfigUpdate {
  enabled: boolean;
  interval_hours: number;
}

export interface NewIncidentSyncResult {
  sync_date: string;
  trigger: string;
  status?: string;
  inserted: number;
  updated: number;
  errors: number;
  total: number;
  comments_posted: number;
  comments_failed: number;
  db_count?: number;
  last_synced_at?: string | null;
  error?: string;
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

export interface ClosedIncidentSyncConfig {
  job_name: string;
  enabled: boolean;
  interval_hours: number;
  last_run_at: string | null;
  last_status: string | null;
  last_result: ClosedIncidentSyncResult | null;
  next_run_at: string | null;
  updated_at: string | null;
}

export interface ClosedIncidentSyncConfigUpdate {
  enabled: boolean;
  interval_hours: number;
}

export interface ClosedIncidentSyncResult {
  target_date: string;
  trigger: string;
  status?: string;
  fetched: number;
  closed: number;
  imported: number;
  updated: number;
  skipped: number;
  failed: number;
  closed_marked: number;
  errors?: string[];
  skipped_lock?: boolean;
  error?: string;
}
