import { useCallback, useState } from 'react';
import { CheckCircle2, RefreshCw } from 'lucide-react';
import { api } from '../api';
import type { ClosedIncidentSyncConfig, ClosedIncidentSyncResult } from '../types';
import { SyncJobPanel } from '../components/sync';
import { useScheduledSyncJob } from '../hooks/useScheduledSyncJob';
import { useSyncDateRange } from '../hooks/useSyncDateRange';
import { validateSyncDateRange } from '../utils/datetime';

interface ClosedIncidentsSyncPageProps {
  onBack?: () => void;
}

export default function ClosedIncidentsSyncPage({ onBack }: ClosedIncidentsSyncPageProps) {
  const { startDate, endDate, setStartDate, setEndDate } = useSyncDateRange('closed-incidents');
  const [syncing, setSyncing] = useState(false);
  const [manualResult, setManualResult] = useState<ClosedIncidentSyncResult | null>(null);

  const {
    config,
    loading,
    error,
    setError,
  } = useScheduledSyncJob<ClosedIncidentSyncConfig>({
    getConfig: api.closedIncidentsConfigGet,
  });

  const rangeError = validateSyncDateRange(startDate, endDate);

  const runSyncNow = useCallback(async () => {
    const validation = validateSyncDateRange(startDate, endDate);
    if (validation) {
      setError(validation);
      return;
    }
    setSyncing(true);
    setError(null);
    try {
      const result = await api.closedIncidentsRun({
        start_date: startDate,
        end_date: endDate,
      });
      setManualResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sync failed');
    } finally {
      setSyncing(false);
    }
  }, [startDate, endDate, setError]);

  const scheduledResult = config?.last_result;

  return (
    <SyncJobPanel<ClosedIncidentSyncResult>
      onBack={onBack}
      error={error || rangeError}
      icon={RefreshCw}
      title="REXUS DB Sync"
      subtitle="Sync closed incidents updated in ServiceNow into the knowledge base (with embeddings)"
      scheduleHint="Scheduled runs sync the window since the last scheduled run"
      syncButtonLabel="Sync Now"
      syncLoadingLabel="Syncing..."
      onSyncNow={() => void runSyncNow()}
      syncDisabled={loading || !!rangeError}
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
          {result.imported} imported, {result.updated} updated,{' '}
          {result.closed_marked} marked closed in new-incidents table
        </p>
      )}
      renderLastResultDetail={(result) => (
        <>
          <div className="flex items-center gap-2 text-slate-700">
            <CheckCircle2 size={10} className="text-emerald-500" />
            <span>
              {result.start_date && result.end_date
                ? `${result.start_date} → ${result.end_date}`
                : `Date ${result.target_date}`}
              : fetched {result.fetched}, closed {result.closed},{' '}
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
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 text-sm text-emerald-800 space-y-1">
          <p>
            Manual sync ({manualResult.start_date ?? startDate} → {manualResult.end_date ?? endDate}):
            fetched {manualResult.fetched}, imported {manualResult.imported}, updated{' '}
            {manualResult.updated}, failed {manualResult.failed}
          </p>
          {manualResult.errors && manualResult.errors.length > 0 && (
            <div className="text-red-600 text-xs max-h-24 overflow-y-auto">
              {manualResult.errors.map((msg, i) => (
                <div key={i}>{msg}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </SyncJobPanel>
  );
}
