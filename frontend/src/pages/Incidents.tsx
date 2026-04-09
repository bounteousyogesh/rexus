import { useEffect, useState, useCallback } from 'react';
import { Search, ChevronLeft, ChevronRight, X } from 'lucide-react';
import { api, type Incident, type PaginatedResponse } from '../api';

export default function IncidentsPage() {
  const [data, setData] = useState<PaginatedResponse<Incident> | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [searchSubmitted, setSearchSubmitted] = useState('');
  const [category, setCategory] = useState('');
  const [cmdbCi, setCmdbCi] = useState('');
  const [selected, setSelected] = useState<Incident | null>(null);
  const [detailData, setDetailData] = useState<Incident | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.incidents({
        page,
        page_size: 20,
        search: searchSubmitted || undefined,
        category: category || undefined,
        cmdb_ci: cmdbCi || undefined,
      });
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load incidents');
    } finally {
      setLoading(false);
    }
  }, [page, searchSubmitted, category, cmdbCi]);

  useEffect(() => { load(); }, [load]);

  const handleSearch = () => {
    setSearchSubmitted(search);
    setPage(1);
  };

  const openDetail = async (inc: Incident) => {
    setSelected(inc);
    try {
      const full = await api.incident(inc.incident_number);
      setDetailData(full);
    } catch {
      setDetailData(null);
    }
  };

  const priorityBadge = (p?: string) => {
    if (!p) return 'bg-slate-100 text-slate-500';
    if (p.includes('1')) return 'bg-red-100 text-red-700';
    if (p.includes('2')) return 'bg-orange-100 text-orange-700';
    if (p.includes('3')) return 'bg-yellow-100 text-yellow-700';
    return 'bg-slate-100 text-slate-600';
  };

  const detail = detailData || selected;

  return (
    <div className="p-6 space-y-4">
      <div>
        <h2 className="text-2xl font-bold text-slate-800">Incidents</h2>
        <p className="text-sm text-slate-500">
          {data ? `${data.total.toLocaleString()} incidents` : 'Loading...'}{' '}
          {(searchSubmitted || category || cmdbCi) && (
            <span className="text-blue-500">(filtered)</span>
          )}
        </p>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <div className="flex-1 min-w-[240px] relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Search descriptions & close notes..."
            className="w-full pl-9 pr-4 py-2.5 bg-white border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        {/* CQ-017: These dropdowns use hardcoded values for simplicity.
            They could be made dynamic by fetching distinct values from the API
            (e.g. GET /api/v1/analytics → categories / top_cmdb_cis). */}
        <select
          value={category}
          onChange={(e) => { setCategory(e.target.value); setPage(1); }}
          className="px-3 py-2.5 bg-white border border-slate-200 rounded-lg text-sm"
        >
          <option value="">All Categories</option>
          <option value="Software">Software</option>
          <option value="Network">Network</option>
          <option value="Hardware">Hardware</option>
          <option value="Information Security">Info Security</option>
        </select>
        <select
          value={cmdbCi}
          onChange={(e) => { setCmdbCi(e.target.value); setPage(1); }}
          className="px-3 py-2.5 bg-white border border-slate-200 rounded-lg text-sm"
        >
          <option value="">All Systems</option>
          <option value="GK POS">GK POS</option>
          <option value="SAP OMS">SAP OMS</option>
          <option value="Vision Service Now Order Updates">Vision SN Order Updates</option>
          <option value="Vision Manual Corrections">Vision Manual Corrections</option>
          <option value="Skybot">Skybot</option>
          <option value="Oracle Retail">Oracle Retail</option>
        </select>
        {(searchSubmitted || category || cmdbCi) && (
          <button
            onClick={() => { setSearch(''); setSearchSubmitted(''); setCategory(''); setCmdbCi(''); setPage(1); }}
            className="flex items-center gap-1 px-3 py-2 text-sm text-red-500 hover:bg-red-50 rounded-lg"
          >
            <X size={14} /> Clear
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-slate-400">Loading...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500 bg-slate-50 border-b border-slate-100">
                  <th className="px-4 py-3 w-28">Incident #</th>
                  <th className="px-4 py-3">Description</th>
                  <th className="px-4 py-3 w-24">Category</th>
                  <th className="px-4 py-3 w-36">System (CMDB)</th>
                  <th className="px-4 py-3 w-24">Priority</th>
                  <th className="px-4 py-3 w-36">Group</th>
                  <th className="px-4 py-3 w-24">Opened</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.map((inc) => (
                  <tr
                    key={inc.id}
                    onClick={() => openDetail(inc)}
                    className="border-b border-slate-50 hover:bg-blue-50/50 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-2.5 font-mono text-xs text-blue-600 whitespace-nowrap">{inc.incident_number}</td>
                    <td className="px-4 py-2.5 text-slate-700 truncate max-w-sm" title={inc.short_description}>{inc.short_description}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-500">{inc.category}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-500 truncate max-w-[140px]" title={inc.cmdb_ci}>{inc.cmdb_ci}</td>
                    <td className="px-4 py-2.5">
                      <span className={`text-xs px-2 py-0.5 rounded-full whitespace-nowrap ${priorityBadge(inc.priority)}`}>
                        {inc.priority || '—'}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-slate-500 truncate max-w-[140px]">{inc.assignment_group}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-500 whitespace-nowrap">
                      {inc.opened_at ? new Date(inc.opened_at).toLocaleDateString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {data && data.pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100 bg-slate-50/50">
            <p className="text-xs text-slate-500">
              Showing {((data.page - 1) * data.page_size) + 1}–{Math.min(data.page * data.page_size, data.total)} of {data.total.toLocaleString()}
            </p>
            <div className="flex items-center gap-1">
              <button onClick={() => setPage(1)} disabled={page <= 1} className="px-2 py-1 text-xs rounded hover:bg-slate-100 disabled:opacity-30">First</button>
              <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page <= 1} className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30"><ChevronLeft size={14} /></button>
              <span className="text-xs text-slate-600 px-2">Page {data.page} of {data.pages.toLocaleString()}</span>
              <button onClick={() => setPage(Math.min(data.pages, page + 1))} disabled={page >= data.pages} className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30"><ChevronRight size={14} /></button>
              <button onClick={() => setPage(data.pages)} disabled={page >= data.pages} className="px-2 py-1 text-xs rounded hover:bg-slate-100 disabled:opacity-30">Last</button>
            </div>
          </div>
        )}
      </div>

      {/* Detail drawer */}
      {selected && (
        <div className="fixed inset-0 z-50 flex justify-end" onClick={() => { setSelected(null); setDetailData(null); }}>
          <div className="bg-black/30 absolute inset-0" />
          <div className="relative bg-white w-[560px] h-full shadow-xl overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="sticky top-0 bg-white border-b border-slate-100 p-4 flex items-center justify-between z-10">
              <div>
                <h3 className="font-semibold text-slate-800">{selected.incident_number}</h3>
                <p className="text-xs text-slate-500">{selected.state}</p>
              </div>
              <button onClick={() => { setSelected(null); setDetailData(null); }} className="p-1 rounded hover:bg-slate-100"><X size={18} /></button>
            </div>
            <div className="p-5 space-y-5">
              <div>
                <p className="text-xs text-slate-500 uppercase tracking-wider">Short Description</p>
                <p className="text-sm text-slate-800 mt-1 font-medium">{detail?.short_description}</p>
              </div>
              {detail?.description && (
                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wider">Description</p>
                  <p className="text-sm text-slate-700 mt-1">{detail.description}</p>
                </div>
              )}
              <div className="grid grid-cols-2 gap-x-6 gap-y-3">
                {[
                  ['Category', detail?.category],
                  ['Subcategory', detail?.subcategory],
                  ['Priority', detail?.priority],
                  ['System (CMDB)', detail?.cmdb_ci],
                  ['Assignment Group', detail?.assignment_group],
                  ['Assigned To', detail?.assigned_to],
                  ['Close Code', detail?.close_code],
                  ['Opened', detail?.opened_at ? new Date(detail.opened_at).toLocaleString() : null],
                  ['Resolved', detail?.resolved_at ? new Date(detail.resolved_at).toLocaleString() : null],
                  ['Closed', detail?.closed_at ? new Date(detail.closed_at).toLocaleString() : null],
                  ['Resolution Time', detail?.business_duration || null],
                ].map(([label, val]) => val ? (
                  <div key={label as string}><p className="text-xs text-slate-500">{label}</p><p className="text-sm font-medium text-slate-700">{val}</p></div>
                ) : null)}
              </div>

              {detail?.cluster && (
                <div className="bg-blue-50 border border-blue-100 rounded-lg p-3">
                  <p className="text-xs text-blue-600 font-medium">Incident Group</p>
                  <p className="text-sm font-semibold text-blue-900">{detail.cluster.cluster_name}</p>
                  <p className="text-xs text-blue-600">Similarity to centroid: {(detail.cluster.similarity_to_centroid * 100).toFixed(0)}%</p>
                </div>
              )}

              {detail?.close_notes && (
                <div>
                  <p className="text-xs text-slate-500 uppercase tracking-wider">Close Notes / Resolution</p>
                  <div className="mt-2 p-3 bg-emerald-50 border border-emerald-100 rounded-lg">
                    <p className="text-sm text-slate-700 whitespace-pre-line">{detail.close_notes}</p>
                  </div>
                </div>
              )}

              {/* SEC-014: work_notes excluded from API response to prevent PII leakage */}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
