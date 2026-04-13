import { useState } from 'react';
import { Search, BarChart3, Layers, Activity, Zap, RefreshCw, Shield, LogOut, KeyRound } from 'lucide-react';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import LoginPage from './pages/Login';
import AuthCallback from './pages/AuthCallback';
import DashboardPage from './pages/Dashboard';
import AnalyzePage from './pages/Analyze';
import IncidentsPage from './pages/Incidents';
import ClustersPage from './pages/Clusters';
import SearchPage from './pages/SearchPage';
import SyncPage from './pages/SyncPage';
import AdminPage from './pages/Admin';
import ChangePassword from './pages/ChangePassword';

type Page = 'dashboard' | 'analyze' | 'sync' | 'incidents' | 'clusters' | 'search' | 'admin';

const NAV: { id: Page; label: string; icon: React.ReactNode; adminOnly?: boolean }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: <BarChart3 size={18} /> },
  { id: 'analyze', label: 'Analyze', icon: <Zap size={18} /> },
  { id: 'sync', label: 'SN Sync', icon: <RefreshCw size={18} /> },
  { id: 'incidents', label: 'Incidents', icon: <Activity size={18} /> },
  { id: 'clusters', label: 'Clusters', icon: <Layers size={18} /> },
  { id: 'search', label: 'Search', icon: <Search size={18} /> },
  { id: 'admin', label: 'Admin', icon: <Shield size={18} />, adminOnly: true },
];

function AuthenticatedApp() {
  const { user, logout } = useAuth();
  const [page, setPage] = useState<Page>('dashboard');
  const [showChangePassword, setShowChangePassword] = useState(false);

  const visibleNav = NAV.filter(
    (item) => !item.adminOnly || user?.role === 'admin',
  );

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
          {visibleNav.map((item) => (
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

        {/* User info + logout at bottom */}
        <div className="p-3 border-t border-slate-700 space-y-1">
          <div className="px-3 py-2 text-sm">
            <div className="font-medium text-white">{user?.username}</div>
            <div className="text-xs text-slate-400 capitalize">{user?.role}</div>
          </div>
          <button
            onClick={() => setShowChangePassword(true)}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <KeyRound size={16} />
            Change Password
          </button>
          <button
            onClick={logout}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-slate-400 hover:text-red-400 hover:bg-slate-800 transition-colors"
          >
            <LogOut size={16} />
            Sign out
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        {page === 'dashboard' && <DashboardPage />}
        {page === 'analyze' && <AnalyzePage />}
        {page === 'sync' && <SyncPage />}
        {page === 'incidents' && <IncidentsPage />}
        {page === 'clusters' && <ClustersPage />}
        {page === 'search' && <SearchPage />}
        {page === 'admin' && <AdminPage />}
      </main>

      {/* Change Password Modal */}
      {showChangePassword && (
        <ChangePassword onClose={() => setShowChangePassword(false)} />
      )}
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppGate />
    </AuthProvider>
  );
}

function AppGate() {
  const { isAuthenticated, isLoading } = useAuth();

  // Handle SSO callback route before anything else
  if (window.location.pathname === '/auth/callback') {
    return <AuthCallback />;
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100">
        <div className="text-slate-500 text-sm">Loading...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return <AuthenticatedApp />;
}
