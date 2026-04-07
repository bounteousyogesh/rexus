import { useState } from 'react';
import { Search, Loader2 } from 'lucide-react';
import { api, type SearchResult } from '../api';

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const data = await api.search(query.trim());
      setResult(data);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-800">Vector Search</h2>
        <p className="text-sm text-slate-500">Semantic search across incidents using AI embeddings</p>
      </div>

      {/* Search bar */}
      <div className="flex gap-3">
        <div className="flex-1 relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Semantic search... e.g. 'SAP IDOC processing failure'"
            className="w-full pl-9 pr-4 py-3 bg-white border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <button
          onClick={handleSearch}
          disabled={loading || !query.trim()}
          className="flex items-center gap-2 px-6 py-3 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-800 disabled:opacity-40 transition-colors"
        >
          {loading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
          Search
        </button>
      </div>

      {/* Results */}
      {result && (
        <div className="space-y-3">
          <p className="text-sm text-slate-500">
            {result.count} result{result.count !== 1 ? 's' : ''} for "{result.query}"
          </p>
          {result.results.map((r) => (
            <div key={r.incident_number} className="bg-white rounded-xl p-5 shadow-sm border border-slate-100 hover:border-blue-200 transition-colors">
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-sm font-medium text-blue-600">{r.incident_number}</span>
                <div className="flex items-center gap-3">
                  {r.cluster_id && (
                    <span className="text-xs px-2 py-0.5 bg-purple-50 text-purple-600 rounded-full">Cluster #{r.cluster_id}</span>
                  )}
                  <span className={`text-sm font-semibold ${
                    r.similarity_score >= 0.7 ? 'text-emerald-600' :
                    r.similarity_score >= 0.5 ? 'text-amber-600' :
                    'text-slate-500'
                  }`}>
                    {(r.similarity_score * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
              <p className="text-sm text-slate-700">{r.short_description}</p>
              {r.close_notes && (
                <div className="mt-3 p-3 bg-slate-50 rounded-lg">
                  <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">Resolution</p>
                  <p className="text-sm text-slate-600 whitespace-pre-line line-clamp-4">{r.close_notes}</p>
                </div>
              )}
              {/* Similarity bar */}
              <div className="mt-3 flex items-center gap-2">
                <div className="flex-1 bg-slate-100 rounded-full h-1.5">
                  <div
                    className={`h-1.5 rounded-full ${
                      r.similarity_score >= 0.7 ? 'bg-emerald-500' :
                      r.similarity_score >= 0.5 ? 'bg-amber-500' :
                      'bg-slate-400'
                    }`}
                    style={{ width: `${r.similarity_score * 100}%` }}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
