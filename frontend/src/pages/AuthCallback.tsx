import { useEffect, useState } from 'react';
import { authApi } from '../api';
import { useAuth } from '../contexts/AuthContext';

export default function AuthCallback() {
  const { loginWithToken } = useAuth();
  const [error, setError] = useState('');
  const [status, setStatus] = useState('Processing SSO login...');

  useEffect(() => {
    async function handleCallback() {
      const params = new URLSearchParams(window.location.search);
      const code = params.get('code');
      const state = params.get('state');
      const errorParam = params.get('error');
      const errorDesc = params.get('error_description');

      // Check for errors from Okta
      if (errorParam) {
        setError(errorDesc || errorParam);
        return;
      }

      if (!code) {
        setError('No authorization code received from identity provider.');
        return;
      }

      // Validate state to prevent CSRF
      const storedState = sessionStorage.getItem('sso_state');
      if (state && storedState && state !== storedState) {
        setError('Invalid state parameter. Please try again.');
        return;
      }

      // Retrieve code_verifier from sessionStorage
      const codeVerifier = sessionStorage.getItem('sso_code_verifier');
      if (!codeVerifier) {
        setError('Missing PKCE code verifier. Please try logging in again.');
        return;
      }

      // Clean up sessionStorage
      sessionStorage.removeItem('sso_code_verifier');
      sessionStorage.removeItem('sso_state');

      try {
        setStatus('Exchanging authorization code...');
        const data = await authApi.ssoCallback(code, codeVerifier);
        // Set token + user directly in AuthContext — avoids a /me round-trip
        // that can 401 if the context hasn't rehydrated yet.
        loginWithToken(data);
        // Replace history so back-button doesn't return to /auth/callback
        window.location.replace('/');
      } catch (err) {
        setError(err instanceof Error ? err.message : 'SSO authentication failed');
      }
    }

    handleCallback();
  }, []);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100">
        <div className="w-full max-w-sm">
          <div className="bg-white rounded-2xl shadow-lg p-8 text-center">
            <div className="bg-red-50 text-red-700 text-sm px-4 py-3 rounded-lg border border-red-200 mb-4">
              {error}
            </div>
            <a
              href="/"
              className="inline-block bg-slate-600 hover:bg-slate-700 text-white font-medium py-2 px-4 rounded-lg text-sm transition-colors"
            >
              Back to Login
            </a>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100">
      <div className="w-full max-w-sm">
        <div className="bg-white rounded-2xl shadow-lg p-8 text-center">
          <div className="flex items-center gap-3 mb-6 justify-center">
            <span className="bg-red-500 text-white w-10 h-10 rounded-lg flex items-center justify-center text-lg font-black">
              R
            </span>
            <div className="text-left">
              <h1 className="text-xl font-bold text-slate-900 leading-tight">REX-US</h1>
              <p className="text-xs text-slate-400">Incident Intelligence</p>
            </div>
          </div>
          <div className="text-slate-500 text-sm">{status}</div>
          <div className="mt-4 flex justify-center">
            <div className="w-6 h-6 border-2 border-slate-300 border-t-red-500 rounded-full animate-spin" />
          </div>
        </div>
      </div>
    </div>
  );
}
