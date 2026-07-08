import { ChevronLeft, ChevronRight } from 'lucide-react';

interface IncidentsPaginationProps {
  page: number;
  pages: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
}

export function IncidentsPagination({
  page,
  pages,
  pageSize,
  total,
  onPageChange,
}: IncidentsPaginationProps) {
  if (pages <= 1) return null;

  return (
    <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100 bg-slate-50/50">
      <p className="text-xs text-slate-500">
        Showing {((page - 1) * pageSize) + 1}–{Math.min(page * pageSize, total)} of {total.toLocaleString()}
      </p>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onPageChange(1)}
          disabled={page <= 1}
          className="px-2 py-1 text-xs rounded hover:bg-slate-100 disabled:opacity-30"
        >
          First
        </button>
        <button
          onClick={() => onPageChange(Math.max(1, page - 1))}
          disabled={page <= 1}
          className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30"
        >
          <ChevronLeft size={14} />
        </button>
        <span className="text-xs text-slate-600 px-2">
          Page {page} of {pages.toLocaleString()}
        </span>
        <button
          onClick={() => onPageChange(Math.min(pages, page + 1))}
          disabled={page >= pages}
          className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30"
        >
          <ChevronRight size={14} />
        </button>
        <button
          onClick={() => onPageChange(pages)}
          disabled={page >= pages}
          className="px-2 py-1 text-xs rounded hover:bg-slate-100 disabled:opacity-30"
        >
          Last
        </button>
      </div>
    </div>
  );
}
