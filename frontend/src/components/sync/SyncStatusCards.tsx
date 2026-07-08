import { Cloud, Clock, Database } from 'lucide-react';
import type { ReactNode } from 'react';
import { formatScheduleTime } from '../../utils/datetime';

interface SyncStatusCardsProps {
  loading: boolean;
  lastRunAt: string | null | undefined;
  lastStatus: string | null | undefined;
  lastRunSummary?: ReactNode;
  scheduleEnabled: boolean;
  intervalHours: number;
  nextRunAt: string | null | undefined;
  scheduleHint: string;
}

export function SyncStatusCards({
  loading,
  lastRunAt,
  lastStatus,
  lastRunSummary,
  scheduleEnabled,
  intervalHours,
  nextRunAt,
  scheduleHint,
}: SyncStatusCardsProps) {
  const lastRun = formatScheduleTime(lastRunAt);
  const nextRun = formatScheduleTime(nextRunAt);
  const status = lastStatus ?? '—';

  return (
    <div className="grid grid-cols-2 gap-4">
      <div className="bg-white rounded-xl p-4 border border-slate-100">
        <div className="flex items-center gap-2 mb-2">
          <Database size={16} className="text-blue-500" />
          <h3 className="text-xs font-semibold text-slate-500 uppercase">Last Run</h3>
        </div>
        {loading ? (
          <p className="text-sm text-slate-400">Loading...</p>
        ) : (
          <div className="space-y-1">
            <p className="text-sm font-medium text-slate-800">{lastRun}</p>
            <p className="text-xs text-slate-500">
              Status: <span className="font-medium">{status}</span>
            </p>
            {lastRunSummary}
          </div>
        )}
      </div>
      <div className="bg-white rounded-xl p-4 border border-slate-100">
        <div className="flex items-center gap-2 mb-2">
          <Cloud size={16} className="text-emerald-500" />
          <h3 className="text-xs font-semibold text-slate-500 uppercase">Automated Schedule</h3>
        </div>
        {loading ? (
          <p className="text-sm text-slate-400">Loading...</p>
        ) : (
          <div className="space-y-1">
            <p className="text-sm font-medium text-slate-800">
              {scheduleEnabled ? `Every ${intervalHours} hour(s)` : 'Disabled'}
            </p>
            <p className="text-xs text-slate-500 flex items-center gap-1">
              <Clock size={12} /> Next run: {scheduleEnabled ? nextRun : '—'}
            </p>
            <p className="text-xs text-slate-400">{scheduleHint}</p>
          </div>
        )}
      </div>
    </div>
  );
}
