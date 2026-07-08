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
  NewIncidentSyncConfigUpdate,
  NewIncidentSyncResult,
} from '../types';
import { SyncJobPanel } from '../components/sync';
import { useScheduledSyncJob } from '../hooks/useScheduledSyncJob';

interface NewIncidentsSyncPageProps {
  onBack?: () => void;
}

export default function NewIncidentsSyncPage({ onBack }: NewIncidentsSyncPageProps) {
  const [preview, setPreview] = useState<NewIncidentsPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [syncedNumbers, setSyncedNumbers] = useState<Set<string>>(new Set());

  const {
    config,
    loading: configLoading,
    saving,
    error,
    setError,
    enabled,
    setEnabled,
    intervalHours,
    setIntervalHours,
    configDirty,
    setConfigDirty,
    loadConfig,
    saveSchedule,
  } = useScheduledSyncJob<NewIncidentSyncConfig, NewIncidentSyncConfigUpdate>({
    getConfig: api.newIncidentsConfigGet,
    setConfig: api.newIncidentsConfigSet,
    buildUpdate: (enabled, interval_hours) => ({ enabled, interval_hours }),
  });

  const loadPreview = useCallback(async () => {
    try {
      setPreview(await api.newIncidentsPreview());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load incidents');
    } finally {
      setPreviewLoading(false);
    }
  }, [setError]);

  useEffect(() => {
    void loadPreview();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void loadPreview();
    }, 60_000);
    return () => window.clearInterval(timer);
  }, [loadPreview]);

  const loading = configLoading || previewLoading;

  const runSync = useCallback(async (incidents: NewIncident[]) => {
    if (!incidents.length) return;
    setSyncing(true);
    setError(null);
    try {
      const numbers = incidents.map((inc) => inc.incident_number);
      await api.newIncidentsRun(numbers);
      setSyncedNumbers((prev) => {
        const next = new Set(prev);
        numbers.forEach((n) => next.add(n));
        return next;
      });
      await Promise.all([loadConfig({ silent: true }), loadPreview()]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sync failed');
    } finally {
      setSyncing(false);
    }
  }, [loadConfig, loadPreview, setError]);

  const runSyncNow = useCallback(async () => {
    const incidents = preview?.incidents ?? [];
    if (!incidents.length) {
      setError('No new incidents to sync');
      return;
    }
    await runSync(incidents);
  }, [preview, runSync, setError]);

  const incidents = preview?.incidents ?? [];
  const groupLabel = preview?.sync_date ?? 'Today';
  const allSynced = incidents.length > 0 && incidents.every((inc) => syncedNumbers.has(inc.incident_number));
  const lastResult = config?.last_result;

  return (
    <SyncJobPanel<NewIncidentSyncResult>
      onBack={onBack}
      error={error}
      icon={RefreshCw}
      title="Sync & Analyze New Incidents"
      subtitle={
        <>
          Opened today in New state — syncs to REXUS, analyzes, and posts a comment on each ticket
          {preview?.sync_date ? ` (${preview.sync_date})` : ''}
        </>
      }
      scheduleHint="Scheduled runs sync and analyze today's new incidents from ServiceNow"
      syncDescription="Sync all new incidents opened today, analyze each, and post REXUS comments"
      syncButtonLabel="Sync Now"
      syncLoadingLabel="Syncing..."
      onSyncNow={() => void runSyncNow()}
      syncDisabled={loading || incidents.length === 0}
      syncing={syncing}
      loading={loading}
      saving={saving}
      enabled={enabled}
      intervalHours={intervalHours}
      configDirty={configDirty}
      lastRunAt={config?.last_run_at}
      lastStatus={config?.last_status}
      nextRunAt={config?.next_run_at}
      scheduleEnabled={config?.enabled ?? false}
      lastResult={lastResult}
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
      onEnabledChange={(value) => {
        setEnabled(value);
        setConfigDirty(true);
      }}
      onIntervalChange={(value) => {
        setIntervalHours(value);
        setConfigDirty(true);
      }}
      onSaveSchedule={() => void saveSchedule()}
    >
      {loading ? (
        <div className="p-8 text-center text-sm text-slate-400">
          <Loader2 size={16} className="animate-spin inline mr-2" />
          Loading incidents...
        </div>
      ) : preview && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm text-slate-600">
              Found <strong>{preview.total}</strong> new incident{preview.total === 1 ? '' : 's'} opened today,{' '}
              <strong className="text-blue-600">{preview.db_count}</strong> synced to database
            </p>
          </div>

          {incidents.length === 0 ? (
            <div className="rounded-xl p-6 text-center border bg-amber-50 border-amber-200">
              <AlertCircle size={28} className="mx-auto text-amber-500 mb-2" />
              <p className="text-sm font-medium text-amber-800">No new incidents for today</p>
            </div>
          ) : (
            <>
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-center justify-between">
                <p className="text-sm font-medium text-amber-800">
                  {incidents.length} new incident{incidents.length === 1 ? '' : 's'} found in ServiceNow
                </p>
                <button
                  onClick={() => void runSync(incidents)}
                  disabled={syncing || allSynced}
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
                    disabled={syncing || allSynced}
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
                    <tbody>
                      {incidents.map((inc) => {
                        const synced = syncedNumbers.has(inc.incident_number);
                        return (
                          <tr key={inc.incident_number} className="border-b border-slate-50">
                            <td className="px-3 py-1.5 font-mono text-blue-600 w-28">{inc.incident_number}</td>
                            <td className="px-3 py-1.5 text-slate-600 truncate max-w-xs">{inc.short_description}</td>
                            <td className="px-3 py-1.5 text-slate-400 w-24">{inc.cmdb_ci || '—'}</td>
                            <td className="px-3 py-1.5 text-slate-400 w-20">{inc.opened_at?.slice(0, 10) || '—'}</td>
                            <td className="px-3 py-1.5 w-16">
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
