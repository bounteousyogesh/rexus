import { useCallback, useEffect, useRef, useState } from 'react';

export interface ScheduledSyncJobConfigBase<TResult = unknown> {
  enabled: boolean;
  interval_hours: number;
  last_run_at: string | null;
  last_status: string | null;
  next_run_at: string | null;
  last_result?: TResult | null;
}

interface UseScheduledSyncJobOptions<TConfig extends ScheduledSyncJobConfigBase, TUpdate> {
  getConfig: () => Promise<TConfig>;
  setConfig: (update: TUpdate) => Promise<TConfig>;
  buildUpdate: (enabled: boolean, intervalHours: number) => TUpdate;
}

export function useScheduledSyncJob<TConfig extends ScheduledSyncJobConfigBase, TUpdate>({
  getConfig,
  setConfig,
  buildUpdate,
}: UseScheduledSyncJobOptions<TConfig, TUpdate>) {
  const [config, setConfigState] = useState<TConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [enabled, setEnabled] = useState(true);
  const [intervalHours, setIntervalHours] = useState(24);
  const [configDirty, setConfigDirty] = useState(false);

  const getConfigRef = useRef(getConfig);
  getConfigRef.current = getConfig;

  const loadConfig = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    setError(null);
    try {
      const data = await getConfigRef.current();
      setConfigState(data);
      setEnabled(data.enabled);
      setIntervalHours(data.interval_hours);
      setConfigDirty(false);
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

  const saveSchedule = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      const data = await setConfig(buildUpdate(enabled, intervalHours));
      setConfigState(data);
      setEnabled(data.enabled);
      setIntervalHours(data.interval_hours);
      setConfigDirty(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save schedule');
    } finally {
      setSaving(false);
    }
  }, [buildUpdate, enabled, intervalHours, setConfig]);

  return {
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
  };
}
