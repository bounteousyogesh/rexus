import { useEffect, useState, useCallback } from 'react';
import {
  RefreshCw, ArrowLeft, CheckCircle2, AlertCircle, Loader2, Database, Play,
} from 'lucide-react';
import { api } from '../api';
import type {
  KbMappingRefreshGroup,
  KbMappingRefreshIncident,
  KbMappingRefreshPreview,
  KbMappingRefreshResult,
  KbMappingRefreshSummary,
  KbArticleFilter,
} from '../types';

interface KbMappingRefreshPageProps {
  onBack: () => void;
}

const KB_FILTER_OPTIONS: { value: KbArticleFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'synced', label: 'Synced' },
  { value: 'not_synced', label: 'Not Synced' },
];

function groupLabel(group: KbMappingRefreshGroup): string {
  return group.day || group.week || group.month || '';
}

function kbStatusLabel(hasKb: boolean | null): { text: string; className: string } {
  if (hasKb === true) return { text: 'Yes', className: 'text-emerald-600' };
  if (hasKb === false) return { text: 'No', className: 'text-slate-500' };
  return { text: '—', className: 'text-amber-600' };
}

function isRefreshSuccess(status: KbMappingRefreshResult['status']): boolean {
  return status === 'mapped' || status === 'no_kb';
}

function RefreshResultIcon({ result }: { result: KbMappingRefreshResult }) {
  if (result.status === 'error' || result.status === 'not_found') {
    const tooltip = result.error || (
      result.status === 'not_found'
        ? 'Incident not found in ServiceNow'
        : 'Refresh failed'
    );
    return (
      <span title={tooltip} className="inline-flex cursor-help">
        <AlertCircle size={12} className="text-red-500" />
      </span>
    );
  }
  if (isRefreshSuccess(result.status)) {
    return <CheckCircle2 size={12} className="text-emerald-500" />;
  }
  return null;
}

function emptySummary(): KbMappingRefreshSummary {
  return {
    candidates: 0,
    with_kb: 0,
    kb_rows_inserted: 0,
    kb_rows_existing: 0,
    no_kb: 0,
    not_found: 0,
    errors: 0,
  };
}

function mergeSummary(a: KbMappingRefreshSummary, b: KbMappingRefreshSummary): KbMappingRefreshSummary {
  return {
    candidates: a.candidates + b.candidates,
    with_kb: a.with_kb + b.with_kb,
    kb_rows_inserted: a.kb_rows_inserted + b.kb_rows_inserted,
    kb_rows_existing: a.kb_rows_existing + b.kb_rows_existing,
    no_kb: a.no_kb + b.no_kb,
    not_found: a.not_found + b.not_found,
    errors: a.errors + b.errors,
  };
}

function applyResults(
  prev: Record<string, KbMappingRefreshResult>,
  results: KbMappingRefreshResult[],
): Record<string, KbMappingRefreshResult> {
  const next = { ...prev };
  for (const r of results) next[r.incident] = r;
  return next;
}

function formatRefreshSummaryMessage(s: KbMappingRefreshSummary): string {
  if (s.candidates === 0) {
    return 'No incidents were selected for refresh.';
  }

  const lines: string[] = [
    `Processed ${s.candidates.toLocaleString()} incident${s.candidates === 1 ? '' : 's'}.`,
  ];

  const outcomes: string[] = [];
  if (s.with_kb > 0) {
    outcomes.push(
      `${s.with_kb.toLocaleString()} had knowledge article${s.with_kb === 1 ? '' : 's'} in ServiceNow`,
    );
  }
  if (s.no_kb > 0) {
    outcomes.push(
      `${s.no_kb.toLocaleString()} had no knowledge articles attached`,
    );
  }
  if (s.not_found > 0) {
    outcomes.push(
      `${s.not_found.toLocaleString()} could not be found in ServiceNow`,
    );
  }
  if (s.errors > 0) {
    outcomes.push(
      `${s.errors.toLocaleString()} failed due to processing errors`,
    );
  }
  if (outcomes.length > 0) {
    lines.push(`${outcomes.join('; ')}.`);
  }

  if (s.kb_rows_inserted > 0) {
    lines.push(
      `${s.kb_rows_inserted.toLocaleString()} new KB mapping${s.kb_rows_inserted === 1 ? '' : 's'} added to the database.`,
    );
  } else if (s.with_kb > 0) {
    lines.push('Existing KB mappings were already up to date; no new rows were inserted.');
  } else {
    lines.push('No KB mappings were added.');
  }

  return lines.join(' ');
}

function refreshSummaryBannerClass(s: KbMappingRefreshSummary): string {
  if (s.errors > 0) {
    return 'text-red-800 bg-red-50 border-red-100';
  }
  if (s.not_found > 0 && s.with_kb === 0 && s.no_kb === 0) {
    return 'text-amber-800 bg-amber-50 border-amber-100';
  }
  return 'text-emerald-800 bg-emerald-50 border-emerald-100';
}

function formatApiError(err: unknown): string {
  if (err instanceof Error) {
    if (err.message.includes('429')) {
      return 'Rate limit exceeded — wait a minute and try again.';
    }
    return err.message;
  }
  return 'Request failed';
}

export default function KbMappingRefreshPage({ onBack }: KbMappingRefreshPageProps) {
  const [kbFilter, setKbFilter] = useState<KbArticleFilter>('not_synced');
  const [preview, setPreview] = useState<KbMappingRefreshPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [refreshMax, setRefreshMax] = useState(500);
  const [groupBy, setGroupBy] = useState<'day' | 'week' | 'month'>('month');
  const [refreshingKey, setRefreshingKey] = useState<string | null>(null);
  const [resultByIncident, setResultByIncident] = useState<Record<string, KbMappingRefreshResult>>({});
  const [lastSummary, setLastSummary] = useState<KbMappingRefreshSummary | null>(null);

  const loadPreview = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    setPreviewError(null);
    try {
      const data = await api.kbMappingRefreshPreview(kbFilter);
      setPreview(data);
    } catch (err) {
      setPreviewError(formatApiError(err));
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  }, [kbFilter]);

  useEffect(() => {
    void api.syncStatus()
      .then((s) => setRefreshMax(s.refresh_max_incidents ?? 500))
      .catch(() => { /* use default batch size */ });
  }, []);

  useEffect(() => {
    void loadPreview();
  }, [loadPreview]);

  const groups: KbMappingRefreshGroup[] = preview
    ? (groupBy === 'month' ? preview.by_month : groupBy === 'week' ? preview.by_week : preview.by_day)
    : [];

  const runRefresh = useCallback(async (incidents: KbMappingRefreshIncident[], key: string) => {
    if (incidents.length === 0) return;
    setRefreshingKey(key);
    setPreviewError(null);
    let batchSummary = emptySummary();
    try {
      for (let i = 0; i < incidents.length; i += refreshMax) {
        const batch = incidents.slice(i, i + refreshMax);
        const numbers = batch.map((inc) => inc.incident_number);
        const data = await api.kbMappingRefreshRun(numbers);
        batchSummary = mergeSummary(batchSummary, data.summary);
        setResultByIncident((prev) => applyResults(prev, data.results));
      }
      setLastSummary(batchSummary);
    } catch (err) {
      setPreviewError(formatApiError(err));
    } finally {
      setRefreshingKey(null);
    }
    await loadPreview({ silent: true });
  }, [refreshMax, loadPreview]);

  return (
    <div className="p-6 space-y-4 max-w-[1000px]">
      <div className="flex items-start gap-3">
        <button
          onClick={onBack}
          className="mt-1 p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors"
          title="Back to Maintenance"
        >
          <ArrowLeft size={18} />
        </button>
        <div>
          <h2 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
            <Database size={22} /> Refresh Knowledge Article Mapping
          </h2>
          <p className="text-sm text-slate-500">
            Check ServiceNow and sync knowledge article links for incidents in the database
          </p>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-slate-100 p-4">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">KA Article Filter</p>
        <div className="flex gap-3 items-end flex-wrap">
          <div>
            <select
              value={kbFilter}
              onChange={(e) => setKbFilter(e.target.value as KbArticleFilter)}
              className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm"
            >
              {KB_FILTER_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
          <button
            onClick={() => loadPreview()}
            disabled={loading || refreshingKey !== null}
            className="flex items-center gap-2 px-5 py-2.5 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-800 disabled:opacity-50"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </div>

      {previewError && (
        <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg p-3">
          <AlertCircle size={16} /> {previewError}
        </div>
      )}

      {lastSummary && refreshingKey === null && (
        <div className={`flex items-start gap-2 text-sm border rounded-lg p-3 ${refreshSummaryBannerClass(lastSummary)}`}>
          <CheckCircle2 size={16} className="shrink-0 mt-0.5" />
          <div>
            <p className="font-medium">Refresh complete</p>
            <p className="mt-0.5 text-[13px] opacity-90">{formatRefreshSummaryMessage(lastSummary)}</p>
          </div>
        </div>
      )}

      {preview && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-slate-600">
            <strong>{preview.total.toLocaleString()}</strong> incidents matching filter
          </p>
          <div className="flex items-center gap-1">
            {(['day', 'week', 'month'] as const).map((g) => (
              <button
                key={g}
                onClick={() => setGroupBy(g)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium ${
                  groupBy === g ? 'bg-slate-200 text-slate-800' : 'text-slate-500 hover:bg-slate-100'
                }`}
              >
                By {g.charAt(0).toUpperCase() + g.slice(1)}
              </button>
            ))}
          </div>
        </div>
      )}

      {preview && (
        <div className="space-y-3">
          {preview.total === 0 ? (
            <div className="rounded-xl p-6 text-center border bg-amber-50 border-amber-200">
              <AlertCircle size={28} className="mx-auto text-amber-500 mb-2" />
              <p className="text-sm font-medium text-amber-800">No incidents match this filter</p>
              <p className="text-xs text-amber-700 mt-1">
                Try a different KA article filter or import incidents via ServiceNow Sync first.
              </p>
            </div>
          ) : (
            <>
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-center justify-between">
                <p className="text-sm font-medium text-amber-800">
                  {preview.total.toLocaleString()} incidents ready for refresh
                </p>
                <button
                  onClick={() => runRefresh(groups.flatMap((g) => g.incidents), '__all__')}
                  disabled={refreshingKey !== null || preview.total === 0}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
                >
                  {refreshingKey === '__all__' ? (
                    <><Loader2 size={14} className="animate-spin" /> Refreshing...</>
                  ) : (
                    <><Play size={14} /> Refresh All ({preview.total})</>
                  )}
                </button>
              </div>

              {groups.map((group) => {
                const label = groupLabel(group);
                const isRefreshingThisGroup = refreshingKey === label;
                const completed = group.incidents.filter((i) => {
                  const r = resultByIncident[i.incident_number];
                  return r && isRefreshSuccess(r.status);
                });
                const allComplete = completed.length === group.incidents.length;

                return (
                  <div key={label} className="bg-white rounded-xl border border-slate-100 overflow-hidden">
                    <div className="flex items-center justify-between p-3 bg-slate-50 border-b border-slate-100">
                      <div>
                        <span className="text-sm font-semibold text-slate-700">{label}</span>
                        <span className="text-xs text-slate-500 ml-2">{group.count} incidents</span>
                      </div>
                      <button
                        onClick={() => runRefresh(group.incidents, label)}
                        disabled={refreshingKey !== null || allComplete}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                          allComplete
                            ? 'bg-emerald-100 text-emerald-700'
                            : 'bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-50'
                        }`}
                      >
                        {allComplete ? (
                          <><CheckCircle2 size={12} /> Refreshed</>
                        ) : isRefreshingThisGroup ? (
                          <><Loader2 size={12} className="animate-spin" /> Refreshing...</>
                        ) : (
                          <><Play size={12} /> Refresh {group.count}</>
                        )}
                      </button>
                    </div>
                    <div className="max-h-48 overflow-y-auto">
                      <table className="w-full text-[11px]">
                        <thead>
                          <tr className="border-b border-slate-100 text-slate-400">
                            <th className="px-3 py-1.5 text-left font-medium w-28">Number</th>
                            <th className="px-3 py-1.5 text-left font-medium">Description</th>
                            <th className="px-3 py-1.5 text-left font-medium w-24">CMDB</th>
                            <th className="px-3 py-1.5 text-left font-medium w-20">Date</th>
                            <th className="px-3 py-1.5 text-left font-medium w-16">KB Article</th>
                            <th className="px-3 py-1.5 w-8" />
                          </tr>
                        </thead>
                        <tbody>
                          {group.incidents.map((inc) => {
                            const result = resultByIncident[inc.incident_number];
                            const kb = kbStatusLabel(inc.has_kb_article);
                            return (
                              <tr key={inc.incident_number} className="border-b border-slate-50">
                                <td className="px-3 py-1.5 font-mono text-blue-600">{inc.incident_number}</td>
                                <td className="px-3 py-1.5 text-slate-600 truncate max-w-xs">{inc.short_description}</td>
                                <td className="px-3 py-1.5 text-slate-400">{inc.cmdb_ci}</td>
                                <td className="px-3 py-1.5 text-slate-400">{inc.opened_at?.slice(0, 10)}</td>
                                <td className={`px-3 py-1.5 font-medium ${kb.className}`}>{kb.text}</td>
                                <td className="px-3 py-1.5">
                                  {result && <RefreshResultIcon result={result} />}
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

    </div>
  );
}