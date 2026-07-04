// Authentication context: holds the current user, restores a saved session on
// load, and exposes login/logout. The token is attached to API requests via
// setAuthToken and persisted to localStorage so a refresh keeps you signed in.
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setAuthToken, setRefreshToken, setAuthCallbacks, ApiError } from "@/api/client";
import type { AuthUser, Role } from "@/api/types";

interface AuthState {
  user: AuthUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  hasRole: (min: Role) => boolean;
}

const ROLE_RANK: Record<Role, number> = {
  viewer: 0, procurement: 1, supervisor: 2, planner: 3, admin: 4,
};

const TOKEN_KEY = "plantrack_token";
const REFRESH_KEY = "plantrack_refresh";
const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  // restore session on mount + wire token-refresh callbacks
  useEffect(() => {
    setAuthCallbacks({
      onRefreshed: (access) => localStorage.setItem(TOKEN_KEY, access),
      onLost: () => {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(REFRESH_KEY);
        setUser(null);
      },
    });
    const saved = localStorage.getItem(TOKEN_KEY);
    const savedRefresh = localStorage.getItem(REFRESH_KEY);
    if (!saved) {
      setLoading(false);
      return;
    }
    setAuthToken(saved);
    if (savedRefresh) setRefreshToken(savedRefresh);
    api.me()
      .then((u) => setUser(u))
      .catch(() => {
        setAuthToken(null);
        setRefreshToken(null);
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(REFRESH_KEY);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = async (username: string, password: string) => {
    const res = await api.login(username, password);
    setAuthToken(res.access_token);
    setRefreshToken(res.refresh_token);
    localStorage.setItem(TOKEN_KEY, res.access_token);
    localStorage.setItem(REFRESH_KEY, res.refresh_token);
    const u = await api.me();
    setUser(u);
  };

  const logout = () => {
    const rt = localStorage.getItem(REFRESH_KEY);
    if (rt) { api.logout(rt).catch(() => {}); }
    setAuthToken(null);
    setRefreshToken(null);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    setUser(null);
  };

  const hasRole = (min: Role) => !!user && ROLE_RANK[user.role] >= ROLE_RANK[min];

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, hasRole }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export { ApiError };