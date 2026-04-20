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

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    sessionStorage.setItem(LOGGED_OUT_KEY, '1'); // signal: user just logged out
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
        if (!cancelled) logout();
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token, logout]); // eslint-disable-line react-hooks/exhaustive-deps

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

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user,
        isLoading,
        login,
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
