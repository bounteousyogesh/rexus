import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { Loader2, Settings2 } from 'lucide-react';
import { api } from '../../api';
import {
  fromDatetimeLocalValue,
  futureDatetimeLocalValue,
  localTimeZoneShortName,
  toDatetimeLocalValue,
  validateFutureScheduleStart,
} from '../../utils/datetime';

export type SchedulableSyncJobId = 'new-incidents-sync' | 'rexus-db-sync';

interface ScheduleConfigModalProps {
  jobId: SchedulableSyncJobId;
  onClose: () => void;
}

const TITLES: Record<SchedulableSyncJobId, string> = {
  'new-incidents-sync': 'Sync & Analyze New Incidents',
  'rexus-db-sync': 'REXUS DB Sync',
};

function resolveStartAtLocal(iso: string | null | undefined): string {
  const loaded = toDatetimeLocalValue(iso);
  if (loaded && !validateFutureScheduleStart(loaded)) {
    return loaded;
  }
  return futureDatetimeLocalValue(1);
}

export function ScheduleConfigModal({ jobId, onClose }: ScheduleConfigModalProps) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(true);
  const [intervalHours, setIntervalHours] = useState(24);
  const [startAtLocal, setStartAtLocal] = useState('');
  const [minStartAt, setMinStartAt] = useState(() => futureDatetimeLocalValue(1));

  const startAtError = useMemo(
    () => validateFutureScheduleStart(startAtLocal),
    [startAtLocal],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setMinStartAt(futureDatetimeLocalValue(1));
    try {
      const data =
        jobId === 'new-incidents-sync'
          ? await api.newIncidentsConfigGet()
          : await api.closedIncidentsConfigGet();
      setEnabled(data.enabled);
      setIntervalHours(data.interval_hours);
      setStartAtLocal(resolveStartAtLocal(data.start_at));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load schedule');
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    if (intervalHours < 1 || intervalHours > 168) {
      setError('Interval must be between 1 and 168 hours');
      return;
    }
    const futureError = validateFutureScheduleStart(startAtLocal);
    if (futureError) {
      setError(futureError);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = {
        enabled,
        interval_hours: intervalHours,
        start_at: fromDatetimeLocalValue(startAtLocal),
      };
      if (jobId === 'new-incidents-sync') {
        await api.newIncidentsConfigSet(payload);
      } else {
        await api.closedIncidentsConfigSet(payload);
      }
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save schedule');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-white rounded-xl p-6 w-full max-w-md shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 mb-4">
          <Settings2 size={18} className="text-slate-500" />
          <h3 className="text-lg font-semibold text-slate-900">Schedule Configuration</h3>
        </div>
        <p className="text-xs text-slate-500 mb-4">{TITLES[jobId]}</p>

        {loading ? (
          <div className="py-8 text-center text-sm text-slate-400">
            <Loader2 size={16} className="animate-spin inline mr-2" />
            Loading...
          </div>
        ) : (
          <form onSubmit={(e) => void handleSave(e)} className="space-y-4">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                className="rounded border-slate-300"
              />
              <span className="text-sm text-slate-700">Enabled</span>
            </label>

            <div>
              <label className="block text-xs text-slate-500 mb-1">
                Start at ({localTimeZoneShortName()})
              </label>
              <input
                type="datetime-local"
                value={startAtLocal}
                min={minStartAt}
                onChange={(e) => setStartAtLocal(e.target.value)}
                className={`w-full px-3 py-2 bg-slate-50 border rounded-lg text-sm ${
                  startAtError ? 'border-red-300' : 'border-slate-200'
                }`}
              />
              <p className="text-[11px] text-slate-400 mt-1">
                Shown in your local timezone; saved as UTC on the server. Must be in the future.
                First run aligns to this time, then repeats every interval.
              </p>
              {startAtError && (
                <p className="text-[11px] text-red-600 mt-1">{startAtError}</p>
              )}
            </div>

            <div>
              <label className="block text-xs text-slate-500 mb-1">Interval (hours)</label>
              <input
                type="number"
                min={1}
                max={168}
                value={intervalHours}
                onChange={(e) => setIntervalHours(Number(e.target.value))}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm"
              />
              <p className="text-[11px] text-slate-400 mt-1">Range: 1–168 hours. Default 24.</p>
            </div>

            {error && <div className="text-red-600 text-sm">{error}</div>}

            <div className="flex gap-3 pt-1">
              <button
                type="submit"
                disabled={saving || !!startAtError}
                className="px-4 py-2 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-800 disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Save Schedule'}
              </button>
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 border border-slate-300 rounded-lg text-sm hover:bg-slate-50"
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
