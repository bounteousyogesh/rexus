import { useState } from 'react';
import { Search, BarChart3, Layers, Activity, Zap, RefreshCw } from 'lucide-react';
import DashboardPage from './pages/Dashboard';
import AnalyzePage from './pages/Analyze';
import IncidentsPage from './pages/Incidents';
import ClustersPage from './pages/Clusters';
import SearchPage from './pages/SearchPage';
import SyncPage from './pages/SyncPage';

type Page = 'dashboard' | 'analyze' | 'sync' | 'incidents' | 'clusters' | 'search';

const NAV: { id: Page; label: string; icon: React.ReactNode }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: <BarChart3 size={18} /> },
  { id: 'analyze', label: 'Analyze', icon: <Zap size={18} /> },
  { id: 'sync', label: 'SN Sync', icon: <RefreshCw size={18} /> },
  { id: 'incidents', label: 'Incidents', icon: <Activity size={18} /> },
  { id: 'clusters', label: 'Clusters', icon: <Layers size={18} /> },
  { id: 'search', label: 'Search', icon: <Search size={18} /> },
];

export default function App() {
  const [page, setPage] = useState<Page>('dashboard');

  return (
    <div className="flex h-screen bg-slate-50">
      {/* Sidebar */}
      <aside className="w-56 bg-slate-900 text-white flex flex-col shrink-0">
        <div className="p-5 border-b border-slate-700">
          <h1 className="text-lg font-bold tracking-tight flex items-center gap-2">
            <span className="bg-red-500 text-white w-8 h-8 rounded-lg flex items-center justify-center text-sm font-black">R</span>
            REX-US
          </h1>
          <p className="text-xs text-slate-400 mt-1">Incident Intelligence</p>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {NAV.map((item) => (
            <button
              key={item.id}
              onClick={() => setPage(item.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                page === item.id
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800'
              }`}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </nav>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        {page === 'dashboard' && <DashboardPage />}
        {page === 'analyze' && <AnalyzePage />}
        {page === 'sync' && <SyncPage />}
        {page === 'incidents' && <IncidentsPage />}
        {page === 'clusters' && <ClustersPage />}
        {page === 'search' && <SearchPage />}
      </main>
    </div>
  );
}
