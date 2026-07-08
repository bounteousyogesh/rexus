import { AlertCircle } from 'lucide-react';

interface SyncErrorBannerProps {
  error: string | null;
}

export function SyncErrorBanner({ error }: SyncErrorBannerProps) {
  if (!error) return null;
  return (
    <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg p-3">
      <AlertCircle size={16} /> {error}
    </div>
  );
}
