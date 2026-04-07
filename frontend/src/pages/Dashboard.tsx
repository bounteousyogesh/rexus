import { useEffect, useState } from 'react';
import { Activity, Layers, BookOpen, Database, AlertCircle } from 'lucide-react';
import { api, type Analytics } from '../api';

export default function DashboardPage() {
  const [data, setData] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);
  // ENH-009: Track fetch errors so the user gets an informative message
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    api.analytics()
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load analytics'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex items-center justify-center h-full text-slate-400">Loading analytics...</div>;
  if (error) return (
    <div className="p-8 flex items-center gap-3 text-red-600">
      <AlertCircle size={20} />
      <span>Failed to load analytics: {error}</span>
    </div>
  );
  if (!data) return <div className="p-8 text-red-500">Failed to load analytics</div>;

  const statCards = [
    { label: 'Total Incidents', value: data.overview.total_incidents.toLocaleString(), icon: <Activity size={20} />, color: 'bg-blue-500' },
    { label: 'Clusters', value: data.overview.total_clusters.toLocaleString(), icon: <Layers size={20} />, color: 'bg-emerald-500' },
    { label: 'Playbooks', value: data.overview.total_playbooks.toLocaleString(), icon: <BookOpen size={20} />, color: 'bg-amber-500' },
    { label: 'Embedded', value: data.overview.embedded_incidents.toLocaleString(), icon: <Database size={20} />, color: 'bg-purple-500' },
  ];

  return (
    <div className="p-6 space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-800">Dashboard</h2>
        <p className="text-sm text-slate-500">Incident intelligence overview</p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-4 gap-4">
        {statCards.map((s) => (
          <div key={s.label} className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">{s.label}</p>
                <p className="text-2xl font-bold text-slate-800 mt-1">{s.value}</p>
              </div>
              <div className={`${s.color} text-white p-2.5 rounded-lg`}>{s.icon}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Resolution time stats */}
      {data.resolution_time?.avg_hours && (
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Resolution Time</h3>
          <div className="grid grid-cols-4 gap-4">
            <div><p className="text-xs text-slate-500">Average</p><p className="text-xl font-bold text-slate-800">{data.resolution_time.avg_hours}h</p></div>
            <div><p className="text-xs text-slate-500">Median</p><p className="text-xl font-bold text-slate-800">{data.resolution_time.median_hours}h</p></div>
            <div><p className="text-xs text-slate-500">Min</p><p className="text-xl font-bold text-emerald-600">{data.resolution_time.min_hours}h</p></div>
            <div><p className="text-xs text-slate-500">Max</p><p className="text-xl font-bold text-red-500">{data.resolution_time.max_hours}h</p></div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-6">
        {/* Incidents by Category */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Incidents by Category</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 border-b border-slate-100">
                <th className="pb-2">Category</th>
                <th className="pb-2 text-right">Count</th>
                <th className="pb-2 w-40"></th>
              </tr>
            </thead>
            <tbody>
              {data.categories.map((c) => (
                <tr key={c.category} className="border-b border-slate-50">
                  <td className="py-2 text-slate-700">{c.category || '(none)'}</td>
                  <td className="py-2 text-right font-medium text-slate-800">{c.count.toLocaleString()}</td>
                  <td className="py-2 pl-3">
                    <div className="w-full bg-slate-100 rounded-full h-2">
                      <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${(c.count / data.categories[0].count) * 100}%` }} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Top Systems (CMDB CI) */}
        <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">Top Systems (CMDB CI)</h3>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 border-b border-slate-100">
                <th className="pb-2">System</th>
                <th className="pb-2 text-right">Count</th>
                <th className="pb-2 w-32"></th>
              </tr>
            </thead>
            <tbody>
              {data.top_cmdb_cis.slice(0, 10).map((c) => (
                <tr key={c.cmdb_ci} className="border-b border-slate-50">
                  <td className="py-2 text-slate-700 truncate max-w-[180px]" title={c.cmdb_ci}>{c.cmdb_ci}</td>
                  <td className="py-2 text-right font-medium text-slate-800">{c.count.toLocaleString()}</td>
                  <td className="py-2 pl-3">
                    <div className="w-full bg-slate-100 rounded-full h-2">
                      <div className="bg-emerald-500 h-2 rounded-full" style={{ width: `${(c.count / data.top_cmdb_cis[0].count) * 100}%` }} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Top clusters */}
      <div className="bg-white rounded-xl p-5 shadow-sm border border-slate-100">
        <h3 className="text-sm font-semibold text-slate-700 mb-3">Top Incident Clusters</h3>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-500 border-b border-slate-100">
              <th className="pb-2">Cluster</th>
              <th className="pb-2 text-right">Incidents</th>
              <th className="pb-2 w-40"></th>
            </tr>
          </thead>
          <tbody>
            {data.top_clusters.map((c) => (
              <tr key={c.id} className="border-b border-slate-50">
                <td className="py-2 text-slate-700">{c.cluster_name}</td>
                <td className="py-2 text-right font-medium text-slate-800">{c.incident_count.toLocaleString()}</td>
                <td className="py-2 pl-3">
                  <div className="w-full bg-slate-100 rounded-full h-2">
                    <div className="bg-purple-500 h-2 rounded-full" style={{ width: `${(c.incident_count / data.top_clusters[0].incident_count) * 100}%` }} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
