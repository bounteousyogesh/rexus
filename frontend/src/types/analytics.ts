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
