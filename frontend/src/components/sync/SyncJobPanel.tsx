import { ArrowLeft, Loader2, type LucideIcon } from 'lucide-react';
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
  syncButtonLabel: string;
  syncLoadingLabel: string;
  onSyncNow: () => void;
  syncDisabled?: boolean;
  syncing?: boolean;
  loading: boolean;
  intervalHours: number;
  lastRunAt?: string | null;
  lastStatus?: string | null;
  nextRunAt?: string | null;
  scheduleEnabled: boolean;
  lastResult?: TResult | null;
  renderLastRunSummary?: (result: TResult) => ReactNode;
  renderLastResultDetail?: (result: TResult) => ReactNode;
  dateRangeControls?: ReactNode;
  children?: ReactNode;
}

export function SyncJobPanel<TResult>({
  onBack,
  error,
  icon: Icon,
  title,
  subtitle,
  scheduleHint,
  syncButtonLabel,
  syncLoadingLabel,
  onSyncNow,
  syncDisabled = false,
  syncing = false,
  loading,
  intervalHours,
  lastRunAt,
  lastStatus,
  nextRunAt,
  scheduleEnabled,
  lastResult,
  renderLastRunSummary,
  renderLastResultDetail,
  dateRangeControls,
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

        <div className="bg-white rounded-xl border border-slate-100 p-4">
          <div className="flex flex-wrap items-end gap-4">
            {dateRangeControls}
            <button
              onClick={onSyncNow}
              disabled={syncDisabled || syncing}
              className="ml-auto flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
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
      </div>

      {lastResult && renderLastResultDetail && (
        <SyncLastResultCard>{renderLastResultDetail(lastResult)}</SyncLastResultCard>
      )}

      {children}
    </div>
  );
}
