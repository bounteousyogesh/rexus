import { ArrowLeft, Loader2, Settings2, type LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { SyncErrorBanner } from './SyncErrorBanner';
import { SyncLastResultCard } from './SyncLastResultCard';
import { SyncStatusCards } from './SyncStatusCards';

export interface SyncJobPanelProps<TResult = unknown> {
  onBack?: () => void;
  error?: string | null;
  icon: LucideIcon;
  title: string;
  subtitle: ReactNode;
  scheduleHint: string;
  syncDescription: string;
  syncButtonLabel: string;
  syncLoadingLabel: string;
  onSyncNow: () => void;
  syncDisabled?: boolean;
  syncing?: boolean;
  enabled: boolean;
  intervalHours: number;
  saving: boolean;
  loading: boolean;
  configDirty: boolean;
  lastRunAt?: string | null;
  lastStatus?: string | null;
  nextRunAt?: string | null;
  scheduleEnabled: boolean;
  lastResult?: TResult | null;
  renderLastRunSummary?: (result: TResult) => ReactNode;
  renderLastResultDetail?: (result: TResult) => ReactNode;
  onEnabledChange: (enabled: boolean) => void;
  onIntervalChange: (hours: number) => void;
  onSaveSchedule: () => void;
  syncNowTitle?: string;
  children?: ReactNode;
}

export function SyncJobPanel<TResult>({
  onBack,
  error,
  icon: Icon,
  title,
  subtitle,
  scheduleHint,
  syncDescription,
  syncButtonLabel,
  syncLoadingLabel,
  onSyncNow,
  syncDisabled = false,
  syncing = false,
  enabled,
  intervalHours,
  saving,
  loading,
  configDirty,
  lastRunAt,
  lastStatus,
  nextRunAt,
  scheduleEnabled,
  lastResult,
  renderLastRunSummary,
  renderLastResultDetail,
  onEnabledChange,
  onIntervalChange,
  onSaveSchedule,
  syncNowTitle = 'Sync Now',
  children,
}: SyncJobPanelProps<TResult>) {
  return (
    <div className="p-6 space-y-4 max-w-[1000px]">
      <SyncErrorBanner error={error ?? null} />

      <div className="space-y-4">
        <div className="flex items-start gap-3">
          {onBack && (
            <button
              onClick={onBack}
              className="mt-1 p-1.5 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors"
              title="Back to Maintenance"
            >
              <ArrowLeft size={18} />
            </button>
          )}
          <div>
            <h2 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
              <Icon size={22} /> {title}
            </h2>
            <p className="text-sm text-slate-500">{subtitle}</p>
          </div>
        </div>

        <SyncStatusCards
          loading={loading}
          lastRunAt={lastRunAt}
          lastStatus={lastStatus}
          lastRunSummary={
            lastResult && renderLastRunSummary ? renderLastRunSummary(lastResult) : undefined
          }
          scheduleEnabled={scheduleEnabled}
          intervalHours={intervalHours}
          nextRunAt={nextRunAt}
          scheduleHint={scheduleHint}
        />

        <div className="bg-white rounded-xl border border-slate-100 p-4 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-slate-800">{syncNowTitle}</h3>
              <p className="text-xs text-slate-500 mt-0.5">{syncDescription}</p>
            </div>
            <button
              onClick={onSyncNow}
              disabled={syncDisabled || syncing}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {syncing ? (
                <>
                  <Loader2 size={14} className="animate-spin" /> {syncLoadingLabel}
                </>
              ) : (
                <>
                  <Icon size={14} /> {syncButtonLabel}
                </>
              )}
            </button>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-100 p-4 space-y-4">
          <div className="flex items-center gap-2">
            <Settings2 size={16} className="text-slate-500" />
            <h3 className="text-sm font-semibold text-slate-800">Schedule Configuration</h3>
          </div>
          <div className="flex flex-wrap items-end gap-4">
            <label className="flex items-center gap-2 py-2">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => onEnabledChange(e.target.checked)}
                className="rounded border-slate-300"
              />
              <span className="text-sm text-slate-700">Enabled</span>
            </label>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Interval (hours)</label>
              <input
                type="number"
                min={1}
                max={168}
                value={intervalHours}
                onChange={(e) => onIntervalChange(Number(e.target.value))}
                className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm w-28"
              />
            </div>
            <button
              onClick={onSaveSchedule}
              disabled={saving || loading || !configDirty}
              className="px-4 py-2 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-800 disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Save Schedule'}
            </button>
          </div>
          <p className="text-xs text-slate-400">Default interval is 24 hours. Range: 1–168 hours.</p>
        </div>
      </div>

      {lastResult && renderLastResultDetail && (
        <SyncLastResultCard>{renderLastResultDetail(lastResult)}</SyncLastResultCard>
      )}

      {children}
    </div>
  );
}
