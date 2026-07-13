import type {
  Analytics,
  AnalyzeResult,
  OrderAnalyzeResult,
  AuthUser,
  KbMappingRefreshPreview,
  KbMappingRefreshResponse,
  Cluster,
  Incident,
  KbArticleOption,
  KbArticleFilter,
  LoginResponse,
  PaginatedResponse,
  Playbook,
  SearchResult,
  SSOConfig,
  SyncDelta,
  SyncImportResponse,
  SyncStatus,
  NewIncidentsPreview,
  NewIncidentsRunResponse,
  NewIncidentSyncConfig,
  NewIncidentSyncConfigUpdate,
  ClosedIncidentSyncConfig,
  ClosedIncidentSyncConfigUpdate,
  ClosedIncidentSyncResult,
} from './types';

export type {
  Analytics,
  AnalyzeResult,
  OrderAnalyzeResult,
  AuthUser,
  KbMappingRefreshGroup,
  KbMappingRefreshIncident,
  KbMappingRefreshPreview,
  KbMappingRefreshResponse,
  KbMappingRefreshResult,
  KbMappingRefreshSummary,
  Cluster,
  Incident,
  KbArticleOption,
  KbArticleFilter,
  KbArticle,
  LoginResponse,
  PaginatedResponse,
  Playbook,
  SearchResult,
  SSOConfig,
  SyncDelta,
  SyncDeltaGroup,
  SyncImportResponse,
  SyncImportResult,
  SyncImportStatus,
  SyncIncident,
  SyncStatus,
  NewIncidentsPreview,
  NewIncidentsRunResponse,
  NewIncident,
  ClosedIncidentSyncConfig,
  ClosedIncidentSyncConfigUpdate,
  ClosedIncidentSyncResult,
} from './types';

export const BASE = '/api/v1';

function getAuthToken(): string | null {
  return localStorage.getItem('rexus_token');
}

function authHeaders(): Record<string, string> {
  const token = getAuthToken();
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

function fullUrl(path: string): string {
  return `${window.location.origin}${path}`;
}

// Paths that must never be forwarded to the backend log (health polls, the
// log endpoint itself) — prevents infinite loops and pointless noise.
const _NO_BACKEND_LOG = ['/health', `${BASE}/log/frontend`];

function _shouldBackendLog(url: string): boolean {
  return !_NO_BACKEND_LOG.some(skip => url.includes(skip));
}

function _truncateForLog(value: unknown, maxLen = 400): string | undefined {
  if (value === undefined || value === null) return undefined;
  try {
    const s = typeof value === 'string' ? value : JSON.stringify(value);
    return s.length > maxLen ? s.slice(0, maxLen) + '…' : s;
  } catch {
    return String(value).slice(0, maxLen);
  }
}

function sendToBackendLog(entry: {
  level: string;
  method: string;
  url: string;
  status?: number;
  body?: unknown;
  response?: unknown;
}) {
  if (!_shouldBackendLog(entry.url)) return;
  // Fire-and-forget — never await, never throw
  const payload = {
    level: entry.level,
    method: entry.method,
    url: entry.url,
    status: entry.status,
    body: _truncateForLog(entry.body),
    response: _truncateForLog(entry.response),
    ts: new Date().toISOString(),
  };
  fetch(`${BASE}/log/frontend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(payload),
  }).catch(() => { /* silently ignore log failures */ });
}

function logRequest(method: string, url: string, body?: unknown) {
  const full = fullUrl(url);
  console.debug(`[API] → ${method} ${full}`, body !== undefined ? body : '');
  sendToBackendLog({ level: 'request', method, url: full, body });
}

function logResponse(method: string, url: string, status: number, data: unknown) {
  const full = fullUrl(url);
  if (status >= 400) {
    console.error(`[API] ← ${method} ${full} ${status} ❌`, data);
    sendToBackendLog({ level: 'error', method, url: full, status, response: data });
  } else {
    console.debug(`[API] ← ${method} ${full} ${status} ✓`, data);
    sendToBackendLog({ level: 'success', method, url: full, status, response: data });
  }
}

async function get<T>(path: string): Promise<T> {
  const url = `${BASE}${path}`;
  logRequest('GET', url);
  const res = await fetch(url, { headers: { ...authHeaders() } });
  const data = await res.json();
  logResponse('GET', url, res.status, data);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return data as T;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const url = `${BASE}${path}`;
  logRequest('POST', url, body);
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  logResponse('POST', url, res.status, data);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return data as T;
}

export async function put<T>(path: string, body: unknown): Promise<T> {
  const url = `${BASE}${path}`;
  logRequest('PUT', url, body);
  const res = await fetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  logResponse('PUT', url, res.status, data);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return data as T;
}

export async function del<T>(path: string): Promise<T> {
  const url = `${BASE}${path}`;
  logRequest('DELETE', url);
  const res = await fetch(url, {
    method: 'DELETE',
    headers: { ...authHeaders() },
  });
  const data = await res.json();
  logResponse('DELETE', url, res.status, data);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return data as T;
}

export const api = {
  health: () => fetch('/health').then(r => { if (!r.ok) throw new Error(`API error: ${r.status}`); return r.json() as Promise<{ status: string; database: string; incidents_count: number }>; }),

  incidents: (params?: { page?: number; page_size?: number; category?: string; cmdb_ci?: string; search?: string; kb_article?: string; state?: string; state_group?: 'closed' | 'new' }) => {
    const qs = new URLSearchParams();
    if (params?.page) qs.set('page', String(params.page));
    if (params?.page_size) qs.set('page_size', String(params.page_size));
    if (params?.category) qs.set('category', params.category);
    if (params?.cmdb_ci) qs.set('cmdb_ci', params.cmdb_ci);
    if (params?.search) qs.set('search', params.search);
    if (params?.kb_article?.trim()) qs.set('kb_article', params.kb_article.trim());
    if (params?.state) qs.set('state', params.state);
    if (params?.state_group) qs.set('state_group', params.state_group);
    return get<PaginatedResponse<Incident>>(`/incidents?${qs}`);
  },

  incidentKbArticles: () =>
    get<{ items: KbArticleOption[] }>('/incidents/kb-articles'),

  incident: (number: string) => get<Incident>(`/incidents/${number}`),

  clusters: (params?: { page?: number; page_size?: number; min_size?: number; sort_by?: string }) => {
    const qs = new URLSearchParams();
    if (params?.page) qs.set('page', String(params.page));
    if (params?.page_size) qs.set('page_size', String(params.page_size));
    if (params?.min_size) qs.set('min_size', String(params.min_size));
    if (params?.sort_by) qs.set('sort_by', params.sort_by);
    return get<PaginatedResponse<Cluster>>(`/clusters?${qs}`);
  },

  cluster: (id: number) => get<Cluster & { top_incidents: Incident[]; playbook?: Playbook }>(`/clusters/${id}`),

  playbooks: (params?: { page?: number; status?: string }) => {
    const qs = new URLSearchParams();
    if (params?.page) qs.set('page', String(params.page));
    if (params?.status) qs.set('status', params.status);
    return get<PaginatedResponse<Playbook>>(`/playbooks?${qs}`);
  },

  playbook: (id: number) => get<Playbook>(`/playbooks/${id}`),

  generatePlaybook: (clusterId: number) =>
    post<{ playbook_id: number; content: string; grounding_score: number; source_incident_count: number; extracted_ids: Record<string, string[]> }>(`/playbooks/generate/${clusterId}`, {}),

  search: (q: string, limit = 10, threshold = 0.4) =>
    get<SearchResult>(`/search?q=${encodeURIComponent(q)}&limit=${limit}&threshold=${threshold}`),

  analyze: (ticketJson: Record<string, unknown>, limit = 10) =>
    post<AnalyzeResult>('/analyze', { ticket_json: ticketJson, limit, threshold: 0.4 }),

  analyzeText: (text: string, limit = 10) =>
    post<AnalyzeResult>('/analyze/text', { text, limit, threshold: 0.4 }),

  fetchIncident: (incidentNumber: string) =>
    get<Record<string, unknown>>(`/fetch-incident/${encodeURIComponent(incidentNumber)}`),

  analyzeIncident: (incidentNumber: string, limit = 15) =>
    post<AnalyzeResult>(`/analyze/incident/${encodeURIComponent(incidentNumber)}`, { limit, threshold: 0.4 }),

  analyzeOrder: async (orderNumber: string): Promise<OrderAnalyzeResult> => {
    const res = await fetch(`${BASE}/analyze/order`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ order_number: orderNumber }),
    });
    if (!res.ok) {
      let detail = `API error: ${res.status}`;
      try {
        const body = await res.json();
        if (typeof body?.detail === 'string') detail = body.detail;
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
    return res.json();
  },

  parsePdf: async (file: File): Promise<Record<string, unknown>> => {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${BASE}/parse-pdf`, { method: 'POST', body: form, headers: { ...authHeaders() } });
    if (!res.ok) throw new Error(`PDF parse error: ${res.status}`);
    return res.json();
  },

  analytics: () => get<Analytics>('/analytics'),

  syncStatus: () => get<SyncStatus>('/sync/status'),

  syncDelta: (params: {
    start_date: string;
    end_date: string;
    closed_only: boolean;
    category?: string;
    cmdb_ci?: string;
  }) => {
    const qs = new URLSearchParams();
    qs.set('start_date', params.start_date);
    qs.set('end_date', params.end_date);
    qs.set('closed_only', String(params.closed_only));
    if (params.category) qs.set('category', params.category);
    if (params.cmdb_ci) qs.set('cmdb_ci', params.cmdb_ci);
    return get<SyncDelta>(`/sync/delta?${qs}`);
  },

  syncImport: (incident_numbers: string[]) =>
    post<SyncImportResponse>('/sync/import', { incident_numbers }),

  newIncidentsPreview: (params?: { start_date?: string; end_date?: string; ignore_assignment_group?: boolean }) => {
    const qs = new URLSearchParams();
    if (params?.start_date) qs.set('start_date', params.start_date);
    if (params?.end_date) qs.set('end_date', params.end_date);
    // Always send the flag explicitly so the backend receives the true intent
    qs.set('ignore_assignment_group', String(params?.ignore_assignment_group ?? true));
    const query = qs.toString();
    return get<NewIncidentsPreview>(`/sync/new-incidents/preview${query ? `?${query}` : ''}`);
  },

  newIncidentsRun: (
    incidentNumbers: string[],
    params?: { start_date?: string; end_date?: string },
  ) =>
    post<NewIncidentsRunResponse>('/sync/new-incidents/run', {
      incident_numbers: incidentNumbers,
      start_date: params?.start_date,
      end_date: params?.end_date,
    }),

  newIncidentsConfigGet: () =>
    get<NewIncidentSyncConfig>('/sync/new-incidents/config'),

  newIncidentsConfigSet: (config: NewIncidentSyncConfigUpdate) =>
    put<NewIncidentSyncConfig>('/sync/new-incidents/config', config),

  closedIncidentsConfigGet: () =>
    get<ClosedIncidentSyncConfig>('/sync/closed-incidents/config'),

  closedIncidentsConfigSet: (config: ClosedIncidentSyncConfigUpdate) =>
    put<ClosedIncidentSyncConfig>('/sync/closed-incidents/config', config),

  closedIncidentsRun: (params?: { start_date?: string; end_date?: string }) =>
    post<ClosedIncidentSyncResult>('/sync/closed-incidents/run', {
      start_date: params?.start_date,
      end_date: params?.end_date,
    }),

  kbMappingRefreshPreview: (hasKbFilter: KbArticleFilter = 'not_synced') =>
    get<KbMappingRefreshPreview>(`/kb-mappings/refresh/preview?has_kb_article=${hasKbFilter}`),

  kbMappingRefreshRun: (incident_numbers: string[]) =>
    post<KbMappingRefreshResponse>('/kb-mappings/refresh', { incident_numbers }),

  listWaves: () => get<{ waves: { split_group: string; total: number; from_date: string; to_date: string; with_problem: number; with_notes: number }[] }>('/waves'),

  listWaveIncidents: (wave: string, page = 1, pageSize = 20) =>
    get<PaginatedResponse<{ incident_number: string; short_description: string; category: string; cmdb_ci: string; priority: string; caller_id: string; location: string; opened_at: string; has_problem: boolean; has_resolution: boolean; has_jira: boolean }>>(`/waves/${wave}/incidents?page=${page}&page_size=${pageSize}`),

  getTestIncident: (wave: string, incidentNumber: string) =>
    get<{ incident_number: string; wave: string; input: Record<string, unknown>; actual: Record<string, unknown> }>(`/waves/${wave}/test/${incidentNumber}`),

  submitFeedback: (data: { analysis_id?: number; incident_number?: string; feedback_text: string; feedback_type?: string; input_method?: string; rating?: number }) =>
    post<{ feedback_id: number; status: string }>('/feedback', data),

  transcribeAudio: async (blob: Blob): Promise<string> => {
    const form = new FormData();
    form.append('file', blob, 'recording.webm');
    const res = await fetch(`${BASE}/transcribe`, { method: 'POST', body: form, headers: { ...authHeaders() } });
    if (!res.ok) throw new Error(`Transcription error: ${res.status}`);
    const data = await res.json();
    return data.text;
  },
};

export const authApi = {
  login: async (username: string, password: string): Promise<LoginResponse> => {
    const res = await fetch(`${BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({ detail: 'Login failed' }));
      throw new Error(data.detail || `Login error: ${res.status}`);
    }
    return res.json();
  },

  me: async (): Promise<AuthUser> => {
    const res = await fetch(`${BASE}/auth/me`, { headers: { ...authHeaders() } });
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
  },

  changePassword: async (currentPassword: string, newPassword: string): Promise<{ status: string }> => {
    const res = await fetch(`${BASE}/auth/change-password`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Change failed' }));
      throw new Error(err.detail || `Change password error: ${res.status}`);
    }
    return res.json();
  },

  listUsers: async (): Promise<AuthUser[]> => {
    const res = await fetch(`${BASE}/auth/users`, { headers: { ...authHeaders() } });
    if (!res.ok) throw new Error(`API error: ${res.status}`);
    return res.json();
  },

  createUser: async (data: { username: string; password: string; email?: string; role: string }): Promise<AuthUser> => {
    const res = await fetch(`${BASE}/auth/users`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Create failed' }));
      throw new Error(err.detail || `Create error: ${res.status}`);
    }
    return res.json();
  },

  updateUser: async (id: number, data: { email?: string; role?: string; is_active?: boolean; password?: string }): Promise<AuthUser> => {
    const res = await fetch(`${BASE}/auth/users/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Update failed' }));
      throw new Error(err.detail || `Update error: ${res.status}`);
    }
    return res.json();
  },

  deactivateUser: async (id: number): Promise<{ status: string }> => {
    const res = await fetch(`${BASE}/auth/users/${id}`, {
      method: 'DELETE',
      headers: { ...authHeaders() },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Delete failed' }));
      throw new Error(err.detail || `Delete error: ${res.status}`);
    }
    return res.json();
  },

  ssoConfig: async (): Promise<SSOConfig | null> => {
    try {
      const res = await fetch(`${BASE}/auth/sso/config`);
      if (!res.ok) return null;
      return res.json();
    } catch {
      return null;
    }
  },

  ssoCallback: async (code: string, codeVerifier: string): Promise<LoginResponse> => {
    const res = await fetch(`${BASE}/auth/sso/callback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, code_verifier: codeVerifier }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'SSO authentication failed' }));
      throw new Error(err.detail || 'SSO authentication failed');
    }
    return res.json() as Promise<LoginResponse>;
  },
};
