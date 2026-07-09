import { useCallback, useEffect, useRef, useState } from 'react';

export interface ScheduledSyncJobConfigBase<TResult = unknown> {
  enabled: boolean;
  interval_hours: number;
  start_at?: string | null;
  last_run_at: string | null;
  last_status: string | null;
  next_run_at: string | null;
  last_result?: TResult | null;
}

interface UseScheduledSyncJobOptions<TConfig extends ScheduledSyncJobConfigBase> {
  getConfig: () => Promise<TConfig>;
}

/** Read-only schedule/status loader for sync job pages (editing is via Maintenance modal). */
export function useScheduledSyncJob<TConfig extends ScheduledSyncJobConfigBase>({
  getConfig,
}: UseScheduledSyncJobOptions<TConfig>) {
  const [config, setConfigState] = useState<TConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const getConfigRef = useRef(getConfig);
  getConfigRef.current = getConfig;

  const loadConfig = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    setError(null);
    try {
      const data = await getConfigRef.current();
      setConfigState(data);
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sync config');
      return null;
    } finally {
      if (!opts?.silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadConfig();
  }, [loadConfig]);

  return {
    config,
    loading,
    error,
    setError,
    loadConfig,
  };
}
