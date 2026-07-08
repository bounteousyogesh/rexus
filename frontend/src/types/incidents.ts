export interface KbArticleOption {
  knowledge_article_number: string;
  incident_count: number;
}

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
  opened_by?: string;
  close_notes?: string;
  close_code?: string;
  business_duration?: string;
  opened_at?: string;
  resolved_at?: string;
  closed_at?: string;
  has_kb_article?: boolean | null;
  kb_article_numbers?: string | null;
  similarity_score?: number;
  cluster_id?: number;
  cluster?: { id: number; cluster_name: string; similarity_to_centroid: number };
}
