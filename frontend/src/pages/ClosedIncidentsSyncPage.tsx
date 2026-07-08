import { useCallback, useState } from 'react';
import { CheckCircle2, RefreshCw } from 'lucide-react';
import { api } from '../api';
import type { ClosedIncidentSyncConfig, ClosedIncidentSyncConfigUpdate, ClosedIncidentSyncResult } from '../types';
import { SyncJobPanel } from '../components/sync';
import { useScheduledSyncJob } from '../hooks/useScheduledSyncJob';

interface ClosedIncidentsSyncPageProps {
  onBack?: () => void;
}

export default function ClosedIncidentsSyncPage({ onBack }: ClosedIncidentsSyncPageProps) {
  const [syncing, setSyncing] = useState(false);

  const {
    config,
    loading,
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
  } = useScheduledSyncJob<ClosedIncidentSyncConfig, ClosedIncidentSyncConfigUpdate>({
    getConfig: api.closedIncidentsConfigGet,
    setConfig: api.closedIncidentsConfigSet,
    buildUpdate: (enabled, interval_hours) => ({ enabled, interval_hours }),
  });

  const runSyncNow = useCallback(async () => {
    setSyncing(true);
    setError(null);
    try {
      const today = new Date().toISOString().slice(0, 10);
      await api.closedIncidentsRun(today);
      await loadConfig({ silent: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sync failed');
    } finally {
      setSyncing(false);
    }
  }, [loadConfig, setError]);

  const lastResult = config?.last_result;

  return (
    <SyncJobPanel<ClosedIncidentSyncResult>
      onBack={onBack}
      error={error}
      icon={RefreshCw}
      title="REXUS DB Sync"
      subtitle="Sync closed incidents updated in ServiceNow into the knowledge base (with embeddings)"
      scheduleHint="Scheduled runs process incidents updated yesterday"
      syncDescription="Pull incidents updated today from ServiceNow, import closed ones with embeddings"
      syncButtonLabel="Sync Now"
      syncLoadingLabel="Syncing..."
      onSyncNow={() => void runSyncNow()}
      syncDisabled={loading}
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
          {result.imported} imported, {result.updated} updated,{' '}
          {result.closed_marked} marked closed in new-incidents table
        </p>
      )}
      renderLastResultDetail={(result) => (
        <>
          <div className="flex items-center gap-2 text-slate-700">
            <CheckCircle2 size={10} className="text-emerald-500" />
            <span>
              Date {result.target_date}: fetched {result.fetched}, closed {result.closed},{' '}
              imported {result.imported}, updated {result.updated}, failed {result.failed}
            </span>
          </div>
          {result.errors && result.errors.length > 0 && (
            <div className="mt-2 max-h-32 overflow-y-auto text-red-500 space-y-0.5">
              {result.errors.map((msg, i) => (
                <div key={i}>{msg}</div>
              ))}
            </div>
          )}
        </>
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
    />
  );
}
