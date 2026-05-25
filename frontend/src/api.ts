// ENH-012: Export BASE so other modules can import it instead of duplicating the constant
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

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { ...authHeaders() },
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'DELETE',
    headers: { ...authHeaders() },
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// Types
export interface Incident {
  id: number;
  incident_number: string;
  short_description: string;
  description?: string;
  category?: string;
  subcategory?: string;
  priority?: string;
  state?: string;
  cmdb_ci?: string;
  assignment_group?: string;
  assigned_to?: string;
  close_notes?: string;
  close_code?: string;
  business_duration?: string;
  opened_at?: string;
  resolved_at?: string;
  closed_at?: string;
  similarity_score?: number;
  cluster_id?: number;
  cluster?: { id: number; cluster_name: string; similarity_to_centroid: number };
}

export interface KbArticle {
  sys_id: string;
  number: string;
  short_description: string;
  kb_category_display?: string;
  attached_on?: string;
  url?: string;
  has_pdf?: boolean;
  /** Set on analyze response when PDF was loaded once server-side. */
  pdf_base64?: string;
  kb_title?: string;
  source?: string;
}

export interface Cluster {
  id: number;
  cluster_name: string;
  cluster_description?: string;
  incident_count: number;
  dominant_category?: string;
  avg_resolution_hours?: number;
  avg_internal_similarity?: number;
  status: string;
  created_at: string;
}

export interface Playbook {
  id: number;
  title: string;
  content: string;
  cluster_id?: number;
  cluster_name?: string;
  source_incident_count?: number;
  grounding_score?: number;
  status: string;
}

export interface PaginatedResponse<T> {
  total: number;
  page: number;
  page_size: number;
  pages: number;
  items: T[];
}

export interface AnalyzeResult {
  analysis_id?: number;
  cleaned_issue: string;
  confidence_score: number;
  incident_exists: boolean;
  incident_number?: string;
  match_count: number;
  similar_incidents: Incident[];
  dominant_cluster?: {
    id: number;
    cluster_name: string;
    cluster_description?: string;
    incident_count: number;
    dominant_category?: string;
    avg_resolution_hours?: number;
    avg_internal_similarity?: number;
  };
  focused_playbook: {
    playbook: string;
    notes: string;
    grounding_score: number;
    source_incident_count: number;
    total_similar: number;
    top_problem?: { id: string; count: number };
    secondary_problem?: { id: string; count: number };
    other_problems: string[];
    order_ids: string[];
    jira_tickets: string[];
    kb_articles?: KbArticle[];
    playbook_source?: 'knowledge_article' | 'similar_incidents';
  };
  resolution_patterns: {
    incident_number: string;
    close_notes: string;
    similarity: number;
  }[];
}

export interface SearchResult {
  query: string;
  threshold: number;
  count: number;
  results: {
    incident_id: number;
    incident_number: string;
    short_description: string;
    close_notes?: string;
    similarity_score: number;
    cluster_id?: number;
  }[];
}

export interface Analytics {
  overview: {
    total_incidents: number;
    total_clusters: number;
    total_playbooks: number;
    embedded_incidents: number;
  };
  categories: { category: string; count: number }[];
  top_cmdb_cis: { cmdb_ci: string; count: number }[];
  top_assignment_groups: { assignment_group: string; count: number }[];
  resolution_time: { avg_hours: number; median_hours: number; min_hours: number; max_hours: number };
  top_clusters: { id: number; cluster_name: string; incident_count: number; avg_resolution_hours?: number }[];
  monthly_trend: { month: string; count: number }[];
  states: { state: string; count: number }[];
}

// API methods
export const api = {
  health: () => fetch('/health').then(r => { if (!r.ok) throw new Error(`API error: ${r.status}`); return r.json() as Promise<{ status: string; database: string; incidents_count: number }>; }),

  incidents: (params?: { page?: number; page_size?: number; category?: string; cmdb_ci?: string; search?: string }) => {
    const qs = new URLSearchParams();
    if (params?.page) qs.set('page', String(params.page));
    if (params?.page_size) qs.set('page_size', String(params.page_size));
    if (params?.category) qs.set('category', params.category);
    if (params?.cmdb_ci) qs.set('cmdb_ci', params.cmdb_ci);
    if (params?.search) qs.set('search', params.search);
    return get<PaginatedResponse<Incident>>(`/incidents?${qs}`);
  },

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

  // Enhanced analyze — accepts ServiceNow JSON
  analyze: (ticketJson: Record<string, unknown>, limit = 10) =>
    post<AnalyzeResult>('/analyze', { ticket_json: ticketJson, limit, threshold: 0.4 }),

  // Analyze from plain text
  analyzeText: (text: string, limit = 10) =>
    post<AnalyzeResult>('/analyze/text', { text, limit, threshold: 0.4 }),

  // Fetch incident from ServiceNow (preview before analysis)
  fetchIncident: (incidentNumber: string) =>
    get<Record<string, unknown>>(`/fetch-incident/${encodeURIComponent(incidentNumber)}`),

  // Analyze by INC number — fetch from ServiceNow and analyze in one step
  analyzeIncident: (incidentNumber: string, limit = 15) =>
    post<AnalyzeResult>(`/analyze/incident/${encodeURIComponent(incidentNumber)}`, { limit, threshold: 0.4 }),

  // Upload PDF → get extracted JSON
  parsePdf: async (file: File): Promise<Record<string, unknown>> => {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${BASE}/parse-pdf`, { method: 'POST', body: form, headers: { ...authHeaders() } });
    if (!res.ok) throw new Error(`PDF parse error: ${res.status}`);
    return res.json();
  },

  analytics: () => get<Analytics>('/analytics'),

  // Wave testing
  listWaves: () => get<{ waves: { split_group: string; total: number; from_date: string; to_date: string; with_problem: number; with_notes: number }[] }>('/waves'),

  listWaveIncidents: (wave: string, page = 1, pageSize = 20) =>
    get<PaginatedResponse<{ incident_number: string; short_description: string; category: string; cmdb_ci: string; priority: string; caller_id: string; location: string; opened_at: string; has_problem: boolean; has_resolution: boolean; has_jira: boolean }>>(`/waves/${wave}/incidents?page=${page}&page_size=${pageSize}`),

  getTestIncident: (wave: string, incidentNumber: string) =>
    get<{ incident_number: string; wave: string; input: Record<string, unknown>; actual: Record<string, unknown> }>(`/waves/${wave}/test/${incidentNumber}`),

  // Feedback
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

// ── Auth Types ────────────────────────────────────────────────────

export interface AuthUser {
  id: number;
  username: string;
  role: string;
  email?: string;
  is_active?: boolean;
  must_change_password?: boolean;
  created_at?: string;
  last_login?: string;
}

export interface LoginResponse {
  token: string;
  user: { id: number; username: string; role: string };
}

export interface SSOConfig {
  enabled: boolean;
  client_id?: string;
  authorize_url?: string;
  redirect_uri?: string;
  audience?: string;
}

// ── Auth API ──────────────────────────────────────────────────────

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
