import type { Incident } from './incidents';

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
  /** Similar-incident match % used to select this KB (0–100). */
  match_percent?: number;
  matched_via_incident?: string;
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
    kb_source?: 'incident' | 'similar';
    kb_source_incident?: string;
    kb_match_percent?: number;
    /** Set when playbook text is summarized from a linked knowledge article. */
    playbook_source?: 'knowledge_article' | 'similar_incidents';
  };
  resolution_patterns: {
    incident_number: string;
    close_notes: string;
    similarity: number;
  }[];
}

export interface OrderIncidentCard {
  incident_number: string;
  status: string;
  short_description: string;
  opened_at?: string | null;
  two_line_summary: string[];
  inc_tasks: string[];
  alternate_orders: string[];
  problem_refs: string[];
}

export interface OrderAnalyzeSummary {
  analysis: string;
  accounting_actions: string;
  payment_activities: string;
  solutions: string;
  system_states: string;
}

export interface OrderAnalyzeResult {
  order_number: string;
  incident_count: number;
  message: string;
  incidents: OrderIncidentCard[];
  summary: OrderAnalyzeSummary;
}
