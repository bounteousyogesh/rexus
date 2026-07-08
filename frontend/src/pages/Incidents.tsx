import { useEffect, useState, useCallback } from 'react';
import { Search, X } from 'lucide-react';
import { api } from '../api';
import type { Incident, KbArticleOption, PaginatedResponse } from '../types';
import { IncidentsPagination } from '../components/incidents/IncidentsPagination';
import { priorityBadgeClass } from '../utils/incidents';
import { buildKbArticleUrl } from '../utils/servicenow';

function buildIncidentAnalyzeUrl(incidentNumber: string): string {
  const url = new URL(window.location.origin + window.location.pathname);
  url.searchParams.set('incident', incidentNumber.trim().toUpperCase());
  return url.toString();
}

function KbArticleNumbersCell({ numbers }: { numbers?: string | null }) {
  const trimmed = numbers?.trim();
  if (!trimmed) return <>—</>;

  const articles = trimmed.split(',').map((n) => n.trim()).filter(Boolean);

  return (
    <span onClick={(e) => e.stopPropagation()}>
      {articles.map((num, i) => (
        <span key={num}>
          {i > 0 && ', '}
          <a
            href={buildKbArticleUrl(num)}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 hover:text-blue-800 hover:underline"
            title={`Open ${num} in ServiceNow`}
          >
            {num}
          </a>
        </span>
      ))}
    </span>
  );
}

export type IncidentView = 'closed' | 'new';

interface IncidentsPageProps {
  view: IncidentView;
}

export default function IncidentsPage({ view }: IncidentsPageProps) {
  if (view === 'new') {
    return <NewIncidentsPage />;
  }
  return <ClosedIncidentsPage />;
}

function NewIncidentsPage() {
  const [data, setData] = useState<PaginatedResponse<Incident> | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [searchSubmitted, setSearchSubmitted] = useState('');
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
        state_group: 'new',
      });
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load incidents');
    } finally {
      setLoading(false);
    }
  }, [page, searchSubmitted]);

  useEffect(() => { load(); }, [load]);

  const handleSearch = () => {
    setSearchSubmitted(search);
    setPage(1);
  };

  const hasActiveSearch = Boolean(searchSubmitted);

  return (
    <div className="p-6 space-y-4">
      <div>
        <h2 className="text-2xl font-bold text-slate-800">New Incidents</h2>
        <p className="text-sm text-slate-500">
          {data
            ? `${data.total.toLocaleString()} new incident${data.total === 1 ? '' : 's'}`
            : 'Loading...'}
          {data?.sync_date && (
            <span> — synced {data.sync_date}</span>
          )}
          {hasActiveSearch && (
            <span className="text-blue-500"> (filtered)</span>
          )}
        </p>
      </div>

      <div className="flex gap-3 flex-wrap">
        <div className="flex-1 min-w-[240px] relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={search}
            onChange={(e) => {
              const value = e.target.value;
              setSearch(value);
              if (!value.trim()) {
                setSearchSubmitted('');
                setPage(1);
              }
            }}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Search incident #, description, system, category..."
            className="w-full pl-9 pr-4 py-2.5 bg-white border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        {hasActiveSearch && (
          <button
            onClick={() => {
              setSearch('');
              setSearchSubmitted('');
              setPage(1);
            }}
            className="flex items-center gap-1 px-3 py-2 text-sm text-red-500 hover:bg-red-50 rounded-lg"
          >
            <X size={14} /> Clear
          </button>
        )}
      </div>

      {error && (
        <div className="px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-slate-400">Loading...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500 bg-slate-50 border-b border-slate-100">
                  <th className="px-4 py-3 w-28">Incident #</th>
                  <th className="px-4 py-3 w-36">KA Article #</th>
                  <th className="px-4 py-3">Description</th>
                  <th className="px-4 py-3 w-24">Category</th>
                  <th className="px-4 py-3 w-36">System (CMDB)</th>
                  <th className="px-4 py-3 w-24">Priority</th>
                  <th className="px-4 py-3 w-36">Group</th>
                  <th className="px-4 py-3 w-32">Assigned To</th>
                  <th className="px-4 py-3 w-32">Opened By</th>
                  <th className="px-4 py-3 w-24">Opened</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.length ? data.items.map((inc) => (
                  <tr
                    key={inc.id}
                    className="border-b border-slate-50 hover:bg-blue-50/50 transition-colors"
                  >
                    <td className="px-4 py-2.5 font-mono text-xs whitespace-nowrap">
                      <a
                        href={buildIncidentAnalyzeUrl(inc.incident_number)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:text-blue-800 hover:underline"
                        title={`Analyze ${inc.incident_number}`}
                      >
                        {inc.incident_number}
                      </a>
                    </td>
                    <td
                      className="px-4 py-2.5 font-mono text-xs truncate max-w-[140px]"
                      title={inc.kb_article_numbers ?? undefined}
                    >
                      <KbArticleNumbersCell numbers={inc.kb_article_numbers} />
                    </td>
                    <td className="px-4 py-2.5 text-slate-700 truncate max-w-sm" title={inc.short_description}>{inc.short_description}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-500">{inc.category || '—'}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-500 truncate max-w-[140px]" title={inc.cmdb_ci}>{inc.cmdb_ci || '—'}</td>
                    <td className="px-4 py-2.5">
                      <span className={`text-xs px-2 py-0.5 rounded-full whitespace-nowrap ${priorityBadgeClass(inc.priority)}`}>
                        {inc.priority || '—'}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-slate-500 truncate max-w-[140px]">{inc.assignment_group || '—'}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-500 truncate max-w-[120px]" title={inc.assigned_to}>{inc.assigned_to || '—'}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-500 truncate max-w-[120px]" title={inc.opened_by}>{inc.opened_by || '—'}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-500 whitespace-nowrap">
                      {inc.opened_at ? new Date(inc.opened_at).toLocaleDateString() : '—'}
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={10} className="px-4 py-8 text-center text-slate-400">
                      No new incidents found
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {data && (
          <IncidentsPagination
            page={data.page}
            pages={data.pages}
            pageSize={data.page_size}
            total={data.total}
            onPageChange={setPage}
          />
        )}
      </div>
    </div>
  );
}

function ClosedIncidentsPage() {
  const [data, setData] = useState<PaginatedResponse<Incident> | null>(null);
  const [kbArticleOptions, setKbArticleOptions] = useState<KbArticleOption[]>([]);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [searchSubmitted, setSearchSubmitted] = useState('');
  const [category, setCategory] = useState('');
  const [cmdbCi, setCmdbCi] = useState('');
  const [kbArticle, setKbArticle] = useState('');
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
        kb_article: kbArticle || undefined,
      });
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load incidents');
    } finally {
      setLoading(false);
    }
  }, [page, searchSubmitted, category, cmdbCi, kbArticle]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    api.incidentKbArticles()
      .then((res) => setKbArticleOptions(res.items))
      .catch(() => setKbArticleOptions([]));
  }, []);

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

  const detail = detailData || selected;
  const hasActiveFilters = searchSubmitted || category || cmdbCi || kbArticle;

  return (
    <div className="p-6 space-y-4">
      <div>
        <h2 className="text-2xl font-bold text-slate-800">Closed Incidents</h2>
        <p className="text-sm text-slate-500">
          {data ? `${data.total.toLocaleString()} closed incidents` : 'Loading...'}{' '}
          {hasActiveFilters && (
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
            onChange={(e) => {
              const value = e.target.value;
              setSearch(value);
              if (!value.trim()) {
                setSearchSubmitted('');
                setPage(1);
              }
            }}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Search incident #, descriptions & close notes..."
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
        <select
          value={kbArticle}
          onChange={(e) => { setKbArticle(e.target.value); setPage(1); }}
          className="px-3 py-2.5 bg-white border border-slate-200 rounded-lg text-sm max-w-[200px]"
        >
          <option value="">All KA Articles</option>
          {kbArticleOptions.map((opt) => (
            <option key={opt.knowledge_article_number} value={opt.knowledge_article_number}>
              {opt.knowledge_article_number} ({opt.incident_count})
            </option>
          ))}
        </select>
        {hasActiveFilters && (
          <button
            onClick={() => {
              setSearch('');
              setSearchSubmitted('');
              setCategory('');
              setCmdbCi('');
              setKbArticle('');
              setPage(1);
            }}
            className="flex items-center gap-1 px-3 py-2 text-sm text-red-500 hover:bg-red-50 rounded-lg"
          >
            <X size={14} /> Clear
          </button>
        )}
      </div>
      	{/* Error banner */}
      	{error && (
        	<div className="px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          	{error}
        	</div>
      	)}

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
                  <th className="px-4 py-3 w-36">KA Article #</th>
                  <th className="px-4 py-3">Description</th>
                  <th className="px-4 py-3 w-24">Category</th>
                  <th className="px-4 py-3 w-36">System (CMDB)</th>
                  <th className="px-4 py-3 w-24">Priority</th>
                  <th className="px-4 py-3 w-36">Group</th>
                  <th className="px-4 py-3 w-24">Opened</th>
                </tr>
              </thead>
              <tbody>
                {data?.items.length ? data.items.map((inc) => (
                  <tr
                    key={inc.id}
                    onClick={() => openDetail(inc)}
                    className="border-b border-slate-50 hover:bg-blue-50/50 cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-2.5 font-mono text-xs text-blue-600 whitespace-nowrap">{inc.incident_number}</td>
                    <td
                      className="px-4 py-2.5 font-mono text-xs truncate max-w-[140px]"
                      title={inc.kb_article_numbers ?? undefined}
                    >
                      <KbArticleNumbersCell numbers={inc.kb_article_numbers} />
                    </td>
                    <td className="px-4 py-2.5 text-slate-700 truncate max-w-sm" title={inc.short_description}>{inc.short_description}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-500">{inc.category}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-500 truncate max-w-[140px]" title={inc.cmdb_ci}>{inc.cmdb_ci}</td>
                    <td className="px-4 py-2.5">
                      <span className={`text-xs px-2 py-0.5 rounded-full whitespace-nowrap ${priorityBadgeClass(inc.priority)}`}>
                        {inc.priority || '—'}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-slate-500 truncate max-w-[140px]">{inc.assignment_group}</td>
                    <td className="px-4 py-2.5 text-xs text-slate-500 whitespace-nowrap">
                      {inc.opened_at ? new Date(inc.opened_at).toLocaleDateString() : '—'}
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={8} className="px-4 py-8 text-center text-slate-400">
                      No closed incidents found
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {data && (
          <IncidentsPagination
            page={data.page}
            pages={data.pages}
            pageSize={data.page_size}
            total={data.total}
            onPageChange={setPage}
          />
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
