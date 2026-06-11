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
