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
