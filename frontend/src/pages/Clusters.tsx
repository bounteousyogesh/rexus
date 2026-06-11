import { useEffect, useState, useCallback } from 'react';
import { ChevronLeft, ChevronRight, X, Layers } from 'lucide-react';
import { api } from '../api';
import type { Cluster, Incident, PaginatedResponse, Playbook } from '../types';

// CQ-004: Proper type for cluster detail (extends Cluster with additional fields)
interface ClusterDetail extends Cluster {
  cluster_description?: string;
  problem_ids?: string[];
  avg_resolution_hours?: number;
  top_incidents: Array<Incident & { similarity_to_centroid: number }>;
  playbook?: Playbook | null;
}

export default function ClustersPage() {
  const [data, setData] = useState<PaginatedResponse<Cluster> | null>(null);
  const [page, setPage] = useState(1);
  const [minSize, setMinSize] = useState(5);
  const [selected, setSelected] = useState<ClusterDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [clusterError, setClusterError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.clusters({ page, page_size: 15, min_size: minSize });
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load clusters');
    } finally {
      setLoading(false);
    }
  }, [page, minSize]);

  useEffect(() => { load(); }, [load]);

  const openCluster = async (id: number) => {
    setClusterError(null);
    try {
      const detail = await api.cluster(id);
      setSelected(detail as ClusterDetail);
    } catch (err) {
      setClusterError(err instanceof Error ? err.message : 'Failed to load cluster details');
    }
  };

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-800">Clusters</h2>
          <p className="text-sm text-slate-500">{data?.total ?? '—'} clusters with {minSize}+ incidents</p>
        </div>
        <select
          value={minSize}
          onChange={(e) => { setMinSize(Number(e.target.value)); setPage(1); }}
          className="px-4 py-2 bg-white border border-slate-200 rounded-lg text-sm"
        >
          <option value={1}>All sizes</option>
          <option value={5}>5+ incidents</option>
          <option value={10}>10+ incidents</option>
          <option value={50}>50+ incidents</option>
          <option value={100}>100+ incidents</option>
        </select>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg p-3">
          {error}
        </div>
      )}

      {clusterError && (
        <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg p-3">
          {clusterError}
        </div>
      )}

      {/* Cards grid */}
      {loading ? (
        <div className="p-8 text-center text-slate-400">Loading...</div>
      ) : (
        <div className="grid grid-cols-3 gap-4">
          {data?.items.map((cluster) => (
            <div
              key={cluster.id}
              onClick={() => openCluster(cluster.id)}
              className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 hover:border-blue-200 hover:shadow-md cursor-pointer transition-all"
            >
              <div className="flex items-start justify-between">
                <div className="bg-blue-50 text-blue-600 p-2 rounded-lg">
                  <Layers size={18} />
                </div>
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">{cluster.status}</span>
              </div>
              <h3 className="text-sm font-semibold text-slate-800 mt-3 line-clamp-2">{cluster.cluster_name}</h3>
              <div className="flex items-center gap-4 mt-3 text-xs text-slate-500">
                <span>{cluster.incident_count} incidents</span>
                {cluster.avg_internal_similarity && (
                  <span>Quality: {(cluster.avg_internal_similarity * 100).toFixed(0)}%</span>
                )}
              </div>
              {cluster.dominant_category && (
                <span className="inline-block mt-2 text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-600">{cluster.dominant_category}</span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-slate-500">Page {data.page} of {data.pages}</p>
          <div className="flex gap-2">
            <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page <= 1} className="p-2 rounded-lg bg-white border border-slate-200 hover:bg-slate-50 disabled:opacity-30"><ChevronLeft size={16} /></button>
            <button onClick={() => setPage(Math.min(data.pages, page + 1))} disabled={page >= data.pages} className="p-2 rounded-lg bg-white border border-slate-200 hover:bg-slate-50 disabled:opacity-30"><ChevronRight size={16} /></button>
          </div>
        </div>
      )}

      {/* Cluster detail drawer */}
      {selected && (
        <div className="fixed inset-0 z-50 flex justify-end" onClick={() => setSelected(null)}>
          <div className="bg-black/30 absolute inset-0" />
          <div className="relative bg-white w-[600px] h-full shadow-xl overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="sticky top-0 bg-white border-b border-slate-100 p-4 flex items-center justify-between">
              <h3 className="font-semibold text-slate-800">{selected.cluster_name}</h3>
              <button onClick={() => setSelected(null)} className="p-1 rounded hover:bg-slate-100"><X size={18} /></button>
            </div>
            <div className="p-5 space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-slate-50 rounded-lg p-3"><p className="text-xs text-slate-500">Incidents</p><p className="text-lg font-bold">{selected.incident_count}</p></div>
                <div className="bg-slate-50 rounded-lg p-3"><p className="text-xs text-slate-500">Quality</p><p className="text-lg font-bold">{selected.avg_internal_similarity ? `${(selected.avg_internal_similarity * 100).toFixed(0)}%` : '—'}</p></div>
                <div className="bg-slate-50 rounded-lg p-3"><p className="text-xs text-slate-500">Category</p><p className="text-lg font-bold">{selected.dominant_category || '—'}</p></div>
              </div>

              {(selected.problem_ids ?? []).length > 0 && (
                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wider mb-2">Linked Problems</p>
                  <div className="flex flex-wrap gap-1">
                    {(selected.problem_ids ?? []).map((p: string) => (
                      <span key={p} className="text-xs px-2 py-0.5 bg-amber-50 text-amber-700 rounded-full">{p}</span>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <p className="text-xs text-slate-500 uppercase tracking-wider mb-2">Top Incidents</p>
                <div className="space-y-2">
                  {selected.top_incidents?.slice(0, 10).map((inc) => (
                    <div key={inc.incident_number} className="p-3 bg-slate-50 rounded-lg">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-mono text-blue-600">{inc.incident_number}</span>
                        <span className="text-xs text-slate-500">{(inc.similarity_to_centroid * 100).toFixed(0)}% match</span>
                      </div>
                      <p className="text-sm text-slate-700 mt-1">{inc.short_description}</p>
                      {inc.close_notes && (
                        <p className="text-xs text-slate-500 mt-1 line-clamp-2">{inc.close_notes}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
