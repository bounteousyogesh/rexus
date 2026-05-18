import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from 'react';
import { authApi, type AuthUser, type LoginResponse } from '../api';

interface AuthState {
  user: AuthUser | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  loginWithToken: (data: LoginResponse) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

const TOKEN_KEY = 'rexus_token';
// Set after an explicit logout so AppGate shows the login page instead of
// auto-redirecting to SSO again.
export const LOGGED_OUT_KEY = 'rexus_logged_out';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(
    () => localStorage.getItem(TOKEN_KEY),
  );
  const [isLoading, setIsLoading] = useState(true);
  // Internal: clears auth state when a stored token is found to be invalid on
  // page load. Does NOT set LOGGED_OUT_KEY so AppGate still auto-redirects to SSO.
  const clearSession = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  // Explicit user sign-out: sets LOGGED_OUT_KEY so AppGate shows the login page
  // with the SSO button instead of silently auto-redirecting to Okta again.
  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    sessionStorage.setItem(LOGGED_OUT_KEY, '1');
    setToken(null);
    setUser(null);
  }, []);

  // Validate token on mount only (not on every token change)
  // When login() sets the token, it also sets the user directly — no need to call me()
  useEffect(() => {
    if (!token) {
      setIsLoading(false);
      return;
    }

    // If we already have a user (from login()), skip validation
    if (user) {
      setIsLoading(false);
      return;
    }

    // Only call me() on initial mount with a stored token (page refresh)
    let cancelled = false;
    authApi
      .me()      
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch(() => {
        // Token is expired/invalid — clear it silently so AppGate can
        // auto-redirect to SSO (do NOT set LOGGED_OUT_KEY here).
        if (!cancelled) clearSession();
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token, clearSession]); // eslint-disable-line react-hooks/exhaustive-deps

  const login = useCallback(async (username: string, password: string) => {
    const data: LoginResponse = await authApi.login(username, password);
    localStorage.setItem(TOKEN_KEY, data.token);
    setToken(data.token);
    setUser({
      id: data.user.id,
      username: data.user.username,
      role: data.user.role,
    });
  }, []);

  // Used by AuthCallback after SSO — sets token + user directly, no /me round-trip
  const loginWithToken = useCallback((data: LoginResponse) => {
    localStorage.setItem(TOKEN_KEY, data.token);
    setToken(data.token);
    setUser({
      id: data.user.id,
      username: data.user.username,
      role: data.user.role,
    });
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user,
        isLoading,
        login,
        loginWithToken,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
