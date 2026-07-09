import { useCallback, useEffect, useState } from 'react';
import { todayIsoDate } from '../utils/datetime';

export type SyncDateRangeJobId = 'new-incidents' | 'closed-incidents';

function readStoredRange(storageKey: string): { startDate: string; endDate: string } {
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (raw) {
      const parsed = JSON.parse(raw) as { startDate?: string; endDate?: string };
      if (parsed.startDate && parsed.endDate) {
        return { startDate: parsed.startDate, endDate: parsed.endDate };
      }
    }
  } catch {
    // ignore invalid storage
  }
  const today = todayIsoDate();
  return { startDate: today, endDate: today };
}

/** Per-job date range with session persistence so each sync page keeps its own filter. */
export function useSyncDateRange(jobId: SyncDateRangeJobId) {
  const storageKey = `rexus-sync-date-range:${jobId}`;
  const [range, setRange] = useState(() => readStoredRange(storageKey));

  useEffect(() => {
    sessionStorage.setItem(storageKey, JSON.stringify(range));
  }, [storageKey, range]);

  const setStartDate = useCallback((startDate: string) => {
    setRange((prev) => ({ ...prev, startDate }));
  }, []);

  const setEndDate = useCallback((endDate: string) => {
    setRange((prev) => ({ ...prev, endDate }));
  }, []);

  return { startDate: range.startDate, endDate: range.endDate, setStartDate, setEndDate };
}
