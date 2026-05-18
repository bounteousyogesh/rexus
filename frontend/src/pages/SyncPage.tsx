import { useEffect, useState, useCallback } from 'react';
import { RefreshCw, Download, CheckCircle2, AlertCircle, Loader2, Database, Cloud } from 'lucide-react';
// ENH-012: Import BASE from api.ts instead of duplicating the constant here
import { BASE } from '../api';

// CQ-003: Proper interfaces instead of `any`
interface SyncIncident {
  incident_number: string;
  short_description: string;
  opened_at: string;
  cmdb_ci: string;
  category: string;
}

interface DeltaGroup {
  month?: string;
  week?: string;
  day?: string;
  count: number;
  incidents: SyncIncident[];
}

interface SyncStatus {
  database: {
    total_incidents: number;
    embedded: number;
    latest_incident_date: string | null;
  };
  servicenow: {
    closed_incidents: number | string;
  };
  catalog?: {
    path: string;
    available: boolean;
    date_min: string | null;
    date_max: string | null;
  };
  import_max_incidents?: number;
}

interface SyncDelta {
  total_delta: number;
  total_discovered: number;
  already_in_db: number;
  source: string;
  message?: string | null;
  catalog_date_min?: string | null;
  catalog_date_max?: string | null;
  by_month: DeltaGroup[];
  by_week: DeltaGroup[];
  by_day: DeltaGroup[];
}

interface ImportResult {
  incident: string;
  status: 'imported' | 'error' | 'skipped_not_closed' | 'not_found';
  error?: string;
  state?: string;
}

export default function SyncPage() {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [delta, setDelta] = useState<SyncDelta | null>(null);
  const [loading, setLoading] = useState(false);
  /** Group label (e.g. "2025-03") or "__all__" while that import is in flight */
  const [importingKey, setImportingKey] = useState<string | null>(null);
  const [importResults, setImportResults] = useState<ImportResult[]>([]);
  const [groupBy, setGroupBy] = useState<'day' | 'week' | 'month'>('month');
  const [startDate, setStartDate] = useState(() => {
    const d = new Date(); d.setMonth(d.getMonth() - 6);
    return d.toISOString().slice(0, 10);
  });
  const [endDate, setEndDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [closedOnly, setClosedOnly] = useState(true);
  const [filterCategory, setFilterCategory] = useState('');
  const [filterCmdb, setFilterCmdb] = useState('');
  const [deltaError, setDeltaError] = useState<string | null>(null);

  const checkStatus = useCallback(async () => {
    setStatusError(null);
    try {
      const res = await fetch(`${BASE}/sync/status`);
      if (!res.ok) throw new Error(`Status check failed: ${res.status}`);
      setStatus(await res.json());
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : 'Failed to load sync status');
    }
  }, []);

  const checkDelta = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    setDeltaError(null);
    try {
      const params = new URLSearchParams();
      params.set('start_date', startDate);
      params.set('end_date', endDate);
      params.set('closed_only', String(closedOnly));
      if (filterCategory) params.set('category', filterCategory);
      if (filterCmdb) params.set('cmdb_ci', filterCmdb);
      const res = await fetch(`${BASE}/sync/delta?${params}`);
      if (!res.ok) throw new Error(`Delta check failed: ${res.status}`);
      setDelta(await res.json());
    } catch (err) {
      setDeltaError(err instanceof Error ? err.message : 'Failed to check delta');
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  }, [startDate, endDate, closedOnly, filterCategory, filterCmdb]);

  const refreshAfterImport = useCallback(() => {
    void checkStatus();
    void checkDelta({ silent: true });
  }, [checkStatus, checkDelta]);

  const runImport = useCallback(async (incidents: SyncIncident[], key: string) => {
    const numbers = incidents.map(i => i.incident_number);
    setImportingKey(key);
    try {
      const res = await fetch(`${BASE}/sync/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ incident_numbers: numbers }),
      });
      if (!res.ok) throw new Error(`Import failed: ${res.status}`);
      const data = await res.json();
      setImportResults(prev => [...prev, ...(data.results as ImportResult[])]);
    } catch (err) {
      setDeltaError(err instanceof Error ? err.message : 'Import failed');
    } finally {
      setImportingKey(null);
    }
    refreshAfterImport();
  }, [refreshAfterImport]);

  useEffect(() => { checkStatus(); }, [checkStatus]);

  const groups: DeltaGroup[] = delta ? (groupBy === 'month' ? delta.by_month : groupBy === 'week' ? delta.by_week : delta.by_day) : [];
  const importBatchSize = status?.import_max_incidents ?? 1000;

  return (
    <div className="p-6 space-y-4 max-w-[1000px]">
      <div>
        <h2 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
          <RefreshCw size={22} /> ServiceNow Sync
        </h2>
        <p className="text-sm text-slate-500">Import closed incidents from ServiceNow into the knowledge base</p>
      </div>

      {/* CQ-008: Show error if status fetch failed */}
      {statusError && (
        <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg p-3">
          <AlertCircle size={16} /> {statusError}
        </div>
      )}

      {/* Status cards */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-white rounded-xl p-4 border border-slate-100">
          <div className="flex items-center gap-2 mb-2">
            <Database size={16} className="text-blue-500" />
            <h3 className="text-xs font-semibold text-slate-500 uppercase">Our Database</h3>
          </div>
          {status ? (
            <div className="space-y-1">
              <p className="text-xl font-bold text-slate-800">{status.database.total_incidents?.toLocaleString()}</p>
              <p className="text-xs text-slate-500">
                {status.database.embedded?.toLocaleString()} embedded |
                Latest: {status.database.latest_incident_date?.slice(0, 10) || '—'}
              </p>
              {status.database.total_incidents === 0 && (
                <p className="text-xs text-amber-700 mt-1">
                  Knowledge base is empty — search below and import incidents to populate it.
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-slate-400">Loading...</p>
          )}
        </div>
        <div className="bg-white rounded-xl p-4 border border-slate-100">
          <div className="flex items-center gap-2 mb-2">
            <Cloud size={16} className="text-emerald-500" />
            <h3 className="text-xs font-semibold text-slate-500 uppercase">ServiceNow</h3>
          </div>
          {status ? (
            <div className="space-y-1">
              <p className="text-xl font-bold text-slate-800">{typeof status.servicenow.closed_incidents === 'number' ? status.servicenow.closed_incidents.toLocaleString() : '—'}</p>
              <p className="text-xs text-slate-500">Closed incidents in instance</p>
            </div>
          ) : (
            <p className="text-sm text-slate-400">Loading...</p>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-slate-100 p-4">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Search Filters</p>
        <div className="flex gap-3 items-end flex-wrap">
          <div>
            <label className="block text-xs text-slate-500 mb-1">From</label>
            <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)}
              className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm" />
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">To</label>
            <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)}
              className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm" />
          </div>
          <div className="flex items-center gap-2 py-2">
            <input type="checkbox" id="closedOnly" checked={closedOnly} onChange={e => setClosedOnly(e.target.checked)}
              className="rounded border-slate-300" />
            <label htmlFor="closedOnly" className="text-xs text-slate-600">Closed only</label>
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">Category</label>
            <input value={filterCategory} onChange={e => setFilterCategory(e.target.value)}
              placeholder="e.g. Software" className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm w-32" />
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">System (CMDB CI)</label>
            <input value={filterCmdb} onChange={e => setFilterCmdb(e.target.value)}
              placeholder="e.g. GK POS" className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm w-32" />
          </div>          <button
            onClick={() => checkDelta()}
            disabled={loading}
            className="flex items-center gap-2 px-5 py-2.5 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-800 disabled:opacity-50"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {loading ? 'Searching...' : 'Search ServiceNow'}
          </button>
        </div>
      </div>

      {deltaError && (
        <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg p-3">
          <AlertCircle size={16} /> {deltaError}
        </div>
      )}

      {/* Summary + group toggle */}
      {delta && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-slate-600">
            Found <strong>{delta.total_discovered}</strong> incidents
            <span className="text-slate-400 text-xs ml-1">(source: {delta.source})</span>,{' '}
            <strong>{delta.already_in_db}</strong> already in DB,{' '}
            <strong className="text-blue-600">{delta.total_delta}</strong> new to import
          </p>
          <div className="flex items-center gap-1">
            {(['day', 'week', 'month'] as const).map(g => (
              <button key={g} onClick={() => setGroupBy(g)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium ${groupBy === g ? 'bg-slate-200 text-slate-800' : 'text-slate-500 hover:bg-slate-100'}`}
              >By {g.charAt(0).toUpperCase() + g.slice(1)}</button>
            ))}
          </div>
        </div>
      )}

      {/* Delta results */}
      {delta && (
        <div className="space-y-3">
          {delta.total_delta === 0 ? (
            <div className={`rounded-xl p-6 text-center border ${
              delta.total_discovered === 0
                ? 'bg-amber-50 border-amber-200'
                : 'bg-emerald-50 border-emerald-200'
            }`}>
              {delta.total_discovered === 0 ? (
                <>
                  <AlertCircle size={28} className="mx-auto text-amber-500 mb-2" />
                  <p className="text-sm font-medium text-amber-800">No incidents found for this date range</p>
                  <p className="text-xs text-amber-700 mt-1">
                    {delta.message || 'Try a different date range or check ServiceNow connectivity.'}
                  </p>
                  {delta.catalog_date_min && delta.catalog_date_max && (
                    <p className="text-xs text-amber-600 mt-2">
                      Catalog covers {delta.catalog_date_min} → {delta.catalog_date_max}
                      (e.g. Mar–Apr 2025 has data; May–Jul 2025 is sparse in the export).
                    </p>
                  )}
                </>
              ) : (
                <>
                  <CheckCircle2 size={28} className="mx-auto text-emerald-500 mb-2" />
                  <p className="text-sm font-medium text-emerald-800">All discovered incidents are already imported</p>
                  <p className="text-xs text-emerald-600">
                    {delta.already_in_db} of {delta.total_discovered} in this search are in the database.
                  </p>
                </>
              )}
            </div>
          ) : (
            <>
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-center justify-between">
                <p className="text-sm font-medium text-amber-800">
                  {delta.total_delta} new closed incidents found in ServiceNow
                </p>
                <button
                  onClick={async () => {
                    const allIncs = groups.flatMap((g: DeltaGroup) => g.incidents);
                    setImportingKey('__all__');
                    try {
                      if (allIncs.length > importBatchSize) {
                        for (let i = 0; i < allIncs.length; i += importBatchSize) {
                          const batch = allIncs.slice(i, i + importBatchSize);
                          const numbers = batch.map(inc => inc.incident_number);
                          const res = await fetch(`${BASE}/sync/import`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ incident_numbers: numbers }),
                          });
                          if (!res.ok) throw new Error(`Import failed: ${res.status}`);
                          const data = await res.json();
                          setImportResults(prev => [...prev, ...(data.results as ImportResult[])]);
                        }
                      } else {
                        const numbers = allIncs.map(inc => inc.incident_number);
                        const res = await fetch(`${BASE}/sync/import`, {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ incident_numbers: numbers }),
                        });
                        if (!res.ok) throw new Error(`Import failed: ${res.status}`);
                        const data = await res.json();
                        setImportResults(prev => [...prev, ...(data.results as ImportResult[])]);
                      }
                    } catch (err) {
                      setDeltaError(err instanceof Error ? err.message : 'Import failed');
                    } finally {
                      setImportingKey(null);
                    }
                    refreshAfterImport();
                  }}
                  disabled={importingKey !== null || delta.total_delta === 0}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
                >
                  {importingKey === '__all__' ? (
                    <><Loader2 size={14} className="animate-spin" /> Importing...</>
                  ) : (
                    <><Download size={14} /> Import All ({delta.total_delta})</>
                  )}
                </button>
              </div>

              {groups.map((group: DeltaGroup) => {
                const label = group.day || group.week || group.month || '';
                const isImportingThisGroup = importingKey === label;
                const imported = group.incidents.filter((i: SyncIncident) =>
                  importResults.some(r => r.incident === i.incident_number && r.status === 'imported')
                );
                const allImported = imported.length === group.incidents.length;

                return (
                  <div key={label} className="bg-white rounded-xl border border-slate-100 overflow-hidden">
                    <div className="flex items-center justify-between p-3 bg-slate-50 border-b border-slate-100">
                      <div>
                        <span className="text-sm font-semibold text-slate-700">{label}</span>
                        <span className="text-xs text-slate-500 ml-2">{group.count} incidents</span>
                      </div>
                      <button
                        onClick={() => runImport(group.incidents, label)}
                        disabled={importingKey !== null || allImported}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                          allImported
                            ? 'bg-emerald-100 text-emerald-700'
                            : 'bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-50'
                        }`}
                      >
                        {allImported ? (
                          <><CheckCircle2 size={12} /> Imported</>
                        ) : isImportingThisGroup ? (
                          <><Loader2 size={12} className="animate-spin" /> Importing...</>
                        ) : (
                          <><Download size={12} /> Import {group.count}</>
                        )}
                      </button>
                    </div>
                    <div className="max-h-48 overflow-y-auto">
                      <table className="w-full text-[11px]">
                        <tbody>
                          {group.incidents.map((inc: SyncIncident) => {
                            const result = importResults.find(r => r.incident === inc.incident_number);
                            return (
                              <tr key={inc.incident_number} className="border-b border-slate-50">
                                <td className="px-3 py-1.5 font-mono text-blue-600 w-28">{inc.incident_number}</td>
                                <td className="px-3 py-1.5 text-slate-600 truncate max-w-xs">{inc.short_description}</td>
                                <td className="px-3 py-1.5 text-slate-400 w-24">{inc.cmdb_ci}</td>
                                <td className="px-3 py-1.5 text-slate-400 w-20">{inc.opened_at?.slice(0, 10)}</td>
                                <td className="px-3 py-1.5 w-16">
                                  {result?.status === 'imported' && <CheckCircle2 size={12} className="text-emerald-500" />}
                                  {result?.status === 'error' && <AlertCircle size={12} className="text-red-500" />}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                );
              })}
            </>
          )}
        </div>
      )}

      {/* Import log */}
      {importResults.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-100 p-4">
          <h3 className="text-xs font-semibold text-slate-500 uppercase mb-2">Import Log</h3>
          <div className="text-xs space-y-1 max-h-40 overflow-y-auto">
            {importResults.map((r) => (
              <div key={r.incident} className={`flex items-center gap-2 ${r.status === 'imported' ? 'text-emerald-600' : r.status === 'error' ? 'text-red-500' : 'text-slate-500'}`}>
                {r.status === 'imported' ? <CheckCircle2 size={10} /> : <AlertCircle size={10} />}
                <span className="font-mono">{r.incident}</span>: {r.status}
                {r.error && <span className="text-red-400 ml-1">({r.error})</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
