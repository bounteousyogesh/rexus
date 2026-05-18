import { useState, useEffect } from 'react';
import { Search, BarChart3, Layers, Activity, Zap, RefreshCw, Shield, LogOut, KeyRound } from 'lucide-react';
import { AuthProvider, useAuth, LOGGED_OUT_KEY } from './contexts/AuthContext';
import { authApi, type SSOConfig } from './api';
import LoginPage from './pages/Login';
import LoginDevPage from './pages/Login_Dev';
import { isLocalDevelopment } from './env';
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

// ── PKCE Helpers ─────────────────────────────────────────────────────────────

function generateCodeVerifier(): string {
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  return btoa(String.fromCharCode(...array))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}

async function generateCodeChallenge(verifier: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(verifier);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return btoa(String.fromCharCode(...new Uint8Array(digest)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}

async function redirectToSSO(ssoConfig: SSOConfig) {
  const codeVerifier = generateCodeVerifier();
  const codeChallenge = await generateCodeChallenge(codeVerifier);
  const state = crypto.randomUUID();

  sessionStorage.setItem('sso_code_verifier', codeVerifier);
  sessionStorage.setItem('sso_state', state);

  const params = new URLSearchParams({
    client_id: ssoConfig.client_id!,
    response_type: 'code',
    scope: 'openid email profile',
    redirect_uri: ssoConfig.redirect_uri!,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
    state,
  });

  if (ssoConfig.audience) {
    params.set('audience', ssoConfig.audience);
  }

  window.location.href = `${ssoConfig.authorize_url}?${params.toString()}`;
}

// ── AppGate ───────────────────────────────────────────────────────────────────

function AppGate() {
  const { isAuthenticated, isLoading } = useAuth();
  const [ssoChecked, setSsoChecked] = useState(false);

  const isCallback = window.location.pathname === '/auth/callback';
  const hasSsoError = new URLSearchParams(window.location.search).has('sso_error');
  // After an explicit logout, show the login page instead of auto-redirecting
  const didLogOut = sessionStorage.getItem(LOGGED_OUT_KEY) === '1';

  useEffect(() => {
    if (isCallback || isLoading || isAuthenticated || hasSsoError || didLogOut) {
      setSsoChecked(true);
      return;
    }

    authApi.ssoConfig().then((config) => {
      if (config && config.enabled) {
        redirectToSSO(config); // navigates away — component will unmount
      } else {
        setSsoChecked(true);
      }
    }).catch(() => {
      setSsoChecked(true);
    });
  }, [isCallback, isLoading, isAuthenticated, hasSsoError, didLogOut]);

  // Handle SSO callback route — safe to return after all hooks
  if (isCallback) {
    return <AuthCallback />;
  }

  if (isLoading || (!isAuthenticated && !hasSsoError && !ssoChecked)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100">
        <div className="text-slate-500 text-sm">Loading...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return isLocalDevelopment ? <LoginDevPage /> : <LoginPage />;
  }

  return <AuthenticatedApp />;
}
