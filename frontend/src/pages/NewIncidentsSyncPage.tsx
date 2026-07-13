import { useCallback, useEffect, useState } from 'react';
import {
  RefreshCw,
  Loader2,
  Download,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import { api } from '../api';
import type {
  NewIncident,
  NewIncidentsPreview,
  NewIncidentSyncConfig,
  NewIncidentSyncResult,
  NewIncidentsRunResponse,
} from '../types';
import { SyncJobPanel } from '../components/sync';
import { useScheduledSyncJob } from '../hooks/useScheduledSyncJob';
import { useSyncDateRange } from '../hooks/useSyncDateRange';
import { formatScheduleTime, validateSyncDateRange } from '../utils/datetime';

interface NewIncidentsSyncPageProps {
  onBack?: () => void;
}

export default function NewIncidentsSyncPage({ onBack }: NewIncidentsSyncPageProps) {
  const { startDate, endDate, setStartDate, setEndDate } = useSyncDateRange('new-incidents');
  const [preview, setPreview] = useState<NewIncidentsPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncedNumbers, setSyncedNumbers] = useState<Set<string>>(new Set());
  const [manualResult, setManualResult] = useState<NewIncidentsRunResponse | null>(null);

  const {
    config,
    loading: configLoading,
    error,
    setError,
  } = useScheduledSyncJob<NewIncidentSyncConfig>({
    getConfig: api.newIncidentsConfigGet,
  });

  const rangeError = validateSyncDateRange(startDate, endDate);

  const loadPreview = useCallback(async () => {
    const validation = validateSyncDateRange(startDate, endDate);
    if (validation) {
      setPreview(null);
      setPreviewLoading(false);
      return;
    }
    setPreviewLoading(true);
    try {
      setPreview(await api.newIncidentsPreview({ start_date: startDate, end_date: endDate }));
      setSyncedNumbers(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load incidents');
    } finally {
      setPreviewLoading(false);
    }
  }, [startDate, endDate, setError]);

  useEffect(() => {
    void loadPreview();
  }, [loadPreview]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void loadPreview();
    }, 60_000);
    return () => window.clearInterval(timer);
  }, [loadPreview]);

  const loading = configLoading || previewLoading;

  const runSync = useCallback(async (incidents: NewIncident[]) => {
    if (!incidents.length) return;
    const validation = validateSyncDateRange(startDate, endDate);
    if (validation) {
      setError(validation);
      return;
    }
    setSyncing(true);
    setError(null);
    try {
      const numbers = incidents.map((inc) => inc.incident_number);
      const result = await api.newIncidentsRun(numbers, {
        start_date: startDate,
        end_date: endDate,
      });
      setManualResult(result);
      setSyncedNumbers((prev) => {
        const next = new Set(prev);
        numbers.forEach((n) => next.add(n));
        return next;
      });
      await loadPreview();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sync failed');
    } finally {
      setSyncing(false);
    }
  }, [startDate, endDate, loadPreview, setError]);

  const runSyncNow = useCallback(async () => {
    const incidents = preview?.incidents ?? [];
    if (!incidents.length) {
      setError('No new incidents to sync');
      return;
    }
    await runSync(incidents);
  }, [preview, runSync, setError]);

  const incidents = preview?.incidents ?? [];
  const groupLabel =
    startDate === endDate ? startDate : `${startDate} → ${endDate}`;
  const allSynced = incidents.length > 0 && incidents.every((inc) => syncedNumbers.has(inc.incident_number));
  const scheduledResult = config?.last_result;

  return (
    <SyncJobPanel<NewIncidentSyncResult>
      onBack={onBack}
      error={error || rangeError}
      icon={RefreshCw}
      title="Sync & Analyze New Incidents"
      subtitle={
        <>
          New-state incidents in the selected date range — syncs to REXUS, analyzes, and posts a comment on each ticket
        </>
      }
      scheduleHint="Scheduled runs sync the window since the last scheduled run"
      syncButtonLabel="Sync Now"
      syncLoadingLabel="Syncing..."
      onSyncNow={() => void runSyncNow()}
      syncDisabled={loading || !!rangeError || incidents.length === 0}
      syncing={syncing}
      loading={loading}
      intervalHours={config?.interval_hours ?? 24}
      lastRunAt={config?.last_run_at}
      lastStatus={config?.last_status}
      nextRunAt={config?.next_run_at}
      scheduleEnabled={config?.enabled ?? false}
      lastResult={scheduledResult}
      renderLastRunSummary={(result) => (
        <p className="text-xs text-slate-500">
          {result.inserted} inserted, {result.updated} updated,{' '}
          {result.comments_posted} comment(s) posted
        </p>
      )}
      renderLastResultDetail={(result) => (
        <div className="flex items-center gap-2 text-slate-700">
          <CheckCircle2 size={10} className="text-emerald-500" />
          <span>
            Date {result.sync_date}: {result.total} incident(s),{' '}
            {result.inserted} inserted, {result.updated} updated,{' '}
            {result.comments_posted} comment(s) posted, {result.comments_failed} failed
          </span>
        </div>
      )}
      dateRangeControls={
        <>
          <div>
            <label className="block text-xs text-slate-500 mb-1">From</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">To</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm"
            />
          </div>
          <p className="text-xs text-slate-400 pb-2">Max range: 7 days</p>
        </>
      }
    >
      {manualResult && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 text-sm text-emerald-800">
          Manual sync: {manualResult.total} incident(s), {manualResult.inserted} inserted,{' '}
          {manualResult.updated} updated, {manualResult.comments_posted} comment(s) posted
        </div>
      )}

      {loading ? (
        <div className="p-8 text-center text-sm text-slate-400">
          <Loader2 size={16} className="animate-spin inline mr-2" />
          Loading incidents...
        </div>
      ) : preview && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm text-slate-600">
              Found <strong>{preview.total}</strong> new incident{preview.total === 1 ? '' : 's'} in range,{' '}
              <strong className="text-blue-600">{preview.db_count}</strong> synced to database
              {preview.assignment_group && (
                <span className="ml-2 text-xs text-slate-400">
                  — assignment group: <strong className="text-slate-500">{preview.assignment_group}</strong>
                </span>
              )}
            </p>
          </div>

          {incidents.length === 0 ? (
            <div className="rounded-xl p-6 text-center border bg-amber-50 border-amber-200">
              <AlertCircle size={28} className="mx-auto text-amber-500 mb-2" />
              <p className="text-sm font-medium text-amber-800">No new incidents in this date range</p>
              {preview.assignment_group && (
                <p className="text-xs text-amber-600 mt-1">
                  Filtered by assignment group: <strong>{preview.assignment_group}</strong>
                </p>
              )}
            </div>
          ) : (
            <>
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-center justify-between">
                <p className="text-sm font-medium text-amber-800">
                  {incidents.length} new incident{incidents.length === 1 ? '' : 's'} found in ServiceNow
                </p>
                <button
                  onClick={() => void runSync(incidents)}
                  disabled={syncing || allSynced || !!rangeError}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
                >
                  {syncing ? (
                    <><Loader2 size={14} className="animate-spin" /> Syncing &amp; analyzing...</>
                  ) : (
                    <><Download size={14} /> Sync &amp; Analyze ({incidents.length})</>
                  )}
                </button>
              </div>

              <div className="bg-white rounded-xl border border-slate-100 overflow-hidden">
                <div className="flex items-center justify-between p-3 bg-slate-50 border-b border-slate-100">
                  <div>
                    <span className="text-sm font-semibold text-slate-700">{groupLabel}</span>
                    <span className="text-xs text-slate-500 ml-2">{incidents.length} incidents</span>
                  </div>
                  <button
                    onClick={() => void runSync(incidents)}
                    disabled={syncing || allSynced || !!rangeError}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                      allSynced
                        ? 'bg-emerald-100 text-emerald-700'
                        : 'bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-50'
                    }`}
                  >
                    {allSynced ? (
                      <><CheckCircle2 size={12} /> Done</>
                    ) : syncing ? (
                      <><Loader2 size={12} className="animate-spin" /> Working...</>
                    ) : (
                      <><Download size={12} /> Sync &amp; Analyze ({incidents.length})</>
                    )}
                  </button>
                </div>
                <div className="max-h-96 overflow-y-auto">
                  <table className="w-full text-[11px]">
                    <thead>
                      <tr className="border-b border-slate-100 text-slate-400">
                        <th className="px-3 py-1.5 text-left font-medium w-28">Number</th>
                        <th className="px-3 py-1.5 text-left font-medium">Description</th>
                        <th className="px-3 py-1.5 text-left font-medium w-24">CMDB</th>
                        <th className="px-3 py-1.5 text-left font-medium w-20">State</th>
                        <th className="px-3 py-1.5 text-left font-medium w-36">Opened</th>
                        <th className="px-3 py-1.5 w-8" />
                      </tr>
                    </thead>
                    <tbody>
                      {incidents.map((inc) => {
                        const synced = syncedNumbers.has(inc.incident_number);
                        return (
                          <tr key={inc.incident_number} className="border-b border-slate-50">
                            <td className="px-3 py-1.5 font-mono text-blue-600">{inc.incident_number}</td>
                            <td className="px-3 py-1.5 text-slate-600 truncate max-w-xs">{inc.short_description}</td>
                            <td className="px-3 py-1.5 text-slate-400">{inc.cmdb_ci || '—'}</td>
                            <td className="px-3 py-1.5 text-slate-600">{inc.state || '—'}</td>
                            <td className="px-3 py-1.5 text-slate-400 whitespace-nowrap">
                              {inc.opened_at ? formatScheduleTime(inc.opened_at) : '—'}
                            </td>
                            <td className="px-3 py-1.5">
                              {synced && <CheckCircle2 size={12} className="text-emerald-500" />}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </SyncJobPanel>
  );
}
