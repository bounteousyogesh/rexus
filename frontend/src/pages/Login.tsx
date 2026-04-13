import { useState, useEffect, type FormEvent } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { authApi, type SSOConfig } from '../api';

// ── PKCE Helpers ────────────────────────────────────────────────

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

// ── Login Page ──────────────────────────────────────────────────

export default function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [ssoConfig, setSsoConfig] = useState<SSOConfig | null>(null);
  const [ssoLoading, setSsoLoading] = useState(false);

  // Check for SSO error passed via URL params (from callback redirect)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const ssoError = params.get('sso_error');
    if (ssoError) {
      setError(ssoError);
      // Clean URL
      window.history.replaceState({}, '', '/');
    }
  }, []);

  // Fetch SSO config on mount
  useEffect(() => {
    authApi.ssoConfig().then((config) => {
      if (config && config.enabled) {
        setSsoConfig(config);
      }
    });
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(username, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  async function handleSSOLogin() {
    if (!ssoConfig) return;
    setSsoLoading(true);
    setError('');

    try {
      const codeVerifier = generateCodeVerifier();
      const codeChallenge = await generateCodeChallenge(codeVerifier);
      const state = crypto.randomUUID();

      // Store PKCE verifier and state for the callback
      sessionStorage.setItem('sso_code_verifier', codeVerifier);
      sessionStorage.setItem('sso_state', state);

      // Build authorization URL
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
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to initiate SSO');
      setSsoLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100">
      <div className="w-full max-w-sm">
        <div className="bg-white rounded-2xl shadow-lg p-8">
          {/* Logo */}
          <div className="flex items-center gap-3 mb-8 justify-center">
            <span className="bg-red-500 text-white w-10 h-10 rounded-lg flex items-center justify-center text-lg font-black">
              R
            </span>
            <div>
              <h1 className="text-xl font-bold text-slate-900 leading-tight">REX-US</h1>
              <p className="text-xs text-slate-400">Incident Intelligence</p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-slate-700 mb-1">
                Username
              </label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                placeholder="Enter username"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-slate-700 mb-1">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                placeholder="Enter password"
              />
            </div>

            {error && (
              <div className="bg-red-50 text-red-700 text-sm px-3 py-2 rounded-lg border border-red-200">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-red-500 hover:bg-red-600 disabled:bg-red-300 text-white font-medium py-2.5 rounded-lg text-sm transition-colors"
            >
              {loading ? 'Signing in...' : 'Sign in'}
            </button>
          </form>

          {/* SSO Button — only shown when SSO is enabled */}
          {ssoConfig && (
            <>
              <div className="relative my-5">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-slate-200" />
                </div>
                <div className="relative flex justify-center text-xs">
                  <span className="bg-white px-3 text-slate-400">or</span>
                </div>
              </div>

              <button
                onClick={handleSSOLogin}
                disabled={ssoLoading}
                className="w-full border border-slate-300 hover:bg-slate-50 disabled:opacity-50 text-slate-700 font-medium py-2.5 rounded-lg text-sm transition-colors flex items-center justify-center gap-2"
              >
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                </svg>
                {ssoLoading ? 'Redirecting...' : 'Sign in with SSO'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
