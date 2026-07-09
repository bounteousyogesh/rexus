import { useState } from 'react';
import { api } from '../api';
import type { OrderAnalyzeResult, OrderIncidentCard } from '../types';
import {
  AlertCircle,
  ClipboardList,
  Hash,
  Loader2,
  Package,
  Search,
  Sparkles,
} from 'lucide-react';

function statusBadgeClass(status: string): string {
  const s = status.toLowerCase();
  if (s.includes('closed') || s.includes('resolved')) {
    return 'bg-emerald-100 text-emerald-800 border-emerald-200';
  }
  if (s.includes('progress') || s.includes('work')) {
    return 'bg-amber-100 text-amber-900 border-amber-200';
  }
  if (s.includes('new') || s.includes('open')) {
    return 'bg-sky-100 text-sky-800 border-sky-200';
  }
  return 'bg-slate-100 text-slate-700 border-slate-200';
}

function ChipList({
  label,
  items,
  emptyLabel,
  tone = 'slate',
}: {
  label: string;
  items: string[];
  emptyLabel?: string;
  tone?: 'slate' | 'violet' | 'teal' | 'rose';
}) {
  const toneClass =
    tone === 'violet'
      ? 'bg-violet-50 text-violet-800 border-violet-100'
      : tone === 'teal'
        ? 'bg-teal-50 text-teal-800 border-teal-100'
        : tone === 'rose'
          ? 'bg-rose-50 text-rose-800 border-rose-100'
          : 'bg-slate-50 text-slate-700 border-slate-100';

  const display = items.length > 0 ? items : emptyLabel ? [emptyLabel] : [];

  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {display.map((item) => (
          <span
            key={item}
            className={`inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-mono border ${toneClass} ${
              items.length === 0 ? 'italic opacity-70' : ''
            }`}
          >
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}

function IncidentOrderCard({ card }: { card: OrderIncidentCard }) {
  return (
    <article className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden hover:shadow-md transition-shadow">
      <div className="px-4 py-3 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <a
            href={`/?incident=${encodeURIComponent(card.incident_number)}`}
            className="font-mono text-sm font-bold text-blue-700 hover:underline truncate"
            title="Open in Incident Analyze"
          >
            {card.incident_number}
          </a>
          <span
            className={`shrink-0 text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border ${statusBadgeClass(
              card.status,
            )}`}
          >
            {card.status || 'Unknown'}
          </span>
        </div>
        {card.opened_at && (
          <span className="text-[10px] text-slate-400">
            Opened {card.opened_at.slice(0, 10)}
          </span>
        )}
      </div>

      <div className="p-4 space-y-4">
        {card.short_description && (
          <p className="text-xs text-slate-500 leading-relaxed">{card.short_description}</p>
        )}

        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-2">
            Two-line Summary
          </p>
          <ul className="space-y-1.5">
            {(card.two_line_summary.length > 0
              ? card.two_line_summary
              : ['No summary available.']
            ).map((line, idx) => (
              <li key={idx} className="text-sm text-slate-700 leading-snug flex gap-2">
                <span className="text-blue-400 mt-1.5 shrink-0 w-1.5 h-1.5 rounded-full bg-blue-400" />
                <span>{line}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="grid sm:grid-cols-3 gap-3 pt-1 border-t border-slate-100">
          <ChipList
            label="INC Tasks"
            items={card.inc_tasks}
            emptyLabel="No INC task found"
            tone="violet"
          />
          <ChipList label="Alternate Orders" items={card.alternate_orders} emptyLabel="None" tone="teal" />
          <ChipList label="Problem Refs" items={card.problem_refs} emptyLabel="None found" tone="rose" />
        </div>
      </div>
    </article>
  );
}

export default function OrderAnalyzePanel() {
  const [orderNumber, setOrderNumber] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<OrderAnalyzeResult | null>(null);

  const handleSearch = async () => {
    setError('');
    const trimmed = orderNumber.trim();
    if (!trimmed) {
      setError('Enter a sales order number.');
      return;
    }
    if (!/^\d+$/.test(trimmed)) {
      setError('Invalid format. Enter digits only (e.g. 5073352821).');
      return;
    }

    setLoading(true);
    setResult(null);
    try {
      const data = await api.analyzeOrder(trimmed);
      setResult(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const summary = result?.summary;
  const hasSummary =
    summary &&
    [summary.analysis, summary.accounting_actions, summary.payment_activities, summary.solutions, summary.system_states].some(
      (v) => (v || '').trim().length > 0,
    );

  return (
    <div className="space-y-5">
      <div className="bg-white border border-slate-200 rounded-xl p-5">
        <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
          Sales Order Number
        </label>
        <div className="flex gap-3">
          <div className="relative flex-1">
            <Hash size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={orderNumber}
              onChange={(e) => {
                const next = e.target.value.replace(/\D/g, '');
                setOrderNumber(next);
                setError('');
                setResult(null);
              }}
              onKeyDown={(e) => e.key === 'Enter' && !loading && handleSearch()}
              placeholder="5073352821"
              inputMode="numeric"
              className="w-full pl-9 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-lg text-lg font-mono tracking-wider focus:outline-none focus:ring-2 focus:ring-blue-500"
              maxLength={50}
              disabled={loading}
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={loading}
            className="flex items-center gap-2 px-6 py-3 bg-slate-900 text-white rounded-lg text-sm font-semibold hover:bg-slate-800 disabled:opacity-40 transition-colors"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
            {loading ? 'Searching...' : 'Search'}
          </button>
        </div>
        <p className="text-xs text-slate-400 mt-2">
          Searches local REXUS records for incidents that explicitly reference this sales order.
        </p>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg p-3">
          <AlertCircle size={16} /> {error}
        </div>
      )}

      {loading && (
        <div className="bg-white border border-slate-100 rounded-xl p-8 flex flex-col items-center gap-3 text-slate-500">
          <Loader2 size={28} className="animate-spin text-blue-500" />
          <p className="text-sm font-medium">Looking up related incidents and generating summaries…</p>
        </div>
      )}

      {result && !loading && (
        <div className="space-y-4">
          <div className="flex items-start gap-3 bg-blue-50 border border-blue-100 rounded-xl p-4">
            <Package size={20} className="text-blue-600 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-blue-900">
                Sales Order {result.order_number}
              </p>
              <p className="text-sm text-blue-800 mt-0.5">
                {result.message ||
                  `Found ${result.incident_count} eligible incident(s) where the sales order appears explicitly.`}
              </p>
            </div>
          </div>

          {hasSummary && (
            <section className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-100 bg-gradient-to-r from-indigo-50 to-white flex items-center gap-2">
                <Sparkles size={16} className="text-indigo-600" />
                <h3 className="text-sm font-bold text-slate-800">Summary</h3>
              </div>
              <div className="p-4 grid sm:grid-cols-2 gap-4">
                {(
                  [
                    ['Analysis', summary!.analysis],
                    ['Accounting Actions', summary!.accounting_actions],
                    ['Payment Activities', summary!.payment_activities],
                    ['Solutions / Conclusions', summary!.solutions],
                    ['System States', summary!.system_states],
                  ] as const
                )
                  .filter(([, text]) => (text || '').trim())
                  .map(([title, text]) => (
                    <div key={title} className={title === 'Analysis' ? 'sm:col-span-2' : ''}>
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1">
                        {title}
                      </p>
                      <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">{text}</p>
                    </div>
                  ))}
              </div>
            </section>
          )}

          {result.incidents.length === 0 ? (
            <div className="bg-white border border-dashed border-slate-200 rounded-xl p-8 text-center text-slate-500 text-sm">
              No eligible incidents matched this sales order in the local database.
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-slate-600">
                <ClipboardList size={16} />
                <h3 className="text-xs font-semibold uppercase tracking-wider">
                  Incidents ({result.incident_count})
                </h3>
              </div>
              <div className="grid gap-4">
                {result.incidents.map((card) => (
                  <IncidentOrderCard key={card.incident_number} card={card} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
