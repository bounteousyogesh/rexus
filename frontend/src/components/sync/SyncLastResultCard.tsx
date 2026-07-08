import type { ReactNode } from 'react';

interface SyncLastResultCardProps {
  children: ReactNode;
}

export function SyncLastResultCard({ children }: SyncLastResultCardProps) {
  return (
    <div className="bg-white rounded-xl border border-slate-100 p-4">
      <h3 className="text-xs font-semibold text-slate-500 uppercase mb-2">Last Sync Result</h3>
      <div className="text-xs space-y-1">{children}</div>
    </div>
  );
}
