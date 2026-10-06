import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { login as loginRequest } from "../api/auth";
import { clearSession, dispatchWorkspaceClear, readSession, saveSession } from "../api/client";
import type { AuthSession, Role } from "../api/types";

interface AuthContextValue {
  readonly session: AuthSession | null;
  readonly user: AuthSession["user"] | null;
  readonly isAuthenticated: boolean;
  readonly login: (email: string, password: string, remember: boolean) => Promise<void>;
  readonly loginAsLocalDemo: () => void;
  readonly logout: () => void;
}

interface AuthProviderProps {
  readonly children: ReactNode;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: Readonly<AuthProviderProps>) {
  const [session, setSession] = useState<AuthSession | null>(() => readSession());
  const [idleWarning, setIdleWarning] = useState(false);

  const login = useCallback(async (email: string, password: string, remember: boolean) => {
    const nextSession = await loginRequest({ email, password });
    const validRoles: readonly Role[] = ["Developer", "Reviewer", "Technical Lead", "Administrator"];
    if (!validRoles.includes(nextSession.user.role)) throw new Error("The account role is not recognized.");
    saveSession(nextSession, remember);
    setSession(nextSession);
  }, []);

  const loginAsLocalDemo = useCallback(() => {
    const id = crypto.randomUUID();
    const nextSession: AuthSession = {
      access_token: `local-demo-${id}`,
      token_type: "Bearer",
      user: { id, email: "demo@local.invalid", full_name: "Local demo", role: "Developer" },
    };
    saveSession(nextSession, false);
    setSession(nextSession);
  }, []);

  const logout = useCallback(() => {
    clearSession();
    setSession(null);
    setIdleWarning(false);
    dispatchWorkspaceClear();
  }, []);

  useEffect(() => {
    const expire = () => logout();
    window.addEventListener("coding-validation:session-expired", expire);
    return () => window.removeEventListener("coding-validation:session-expired", expire);
  }, [logout]);

  useEffect(() => {
    if (!session) return undefined;
    let warningTimer: number;
    let logoutTimer: number;
    const reset = () => {
      window.clearTimeout(warningTimer);
      window.clearTimeout(logoutTimer);
      setIdleWarning(false);
      warningTimer = window.setTimeout(() => setIdleWarning(true), 29 * 60 * 1000);
      logoutTimer = window.setTimeout(logout, 30 * 60 * 1000);
    };
    const activityEvents: Array<keyof WindowEventMap> = ["pointerdown", "keydown", "scroll", "touchstart"];
    activityEvents.forEach((name) => window.addEventListener(name, reset, { passive: true }));
    reset();
    return () => {
      window.clearTimeout(warningTimer);
      window.clearTimeout(logoutTimer);
      activityEvents.forEach((name) => window.removeEventListener(name, reset));
    };
  }, [session, logout]);

  const value = useMemo<AuthContextValue>(() => ({ session, user: session?.user ?? null, isAuthenticated: Boolean(session), login, loginAsLocalDemo, logout }), [session, login, loginAsLocalDemo, logout]);
  return <AuthContext.Provider value={value}>{children}{idleWarning && <dialog open className="idle-warning" aria-labelledby="idle-warning-title"><h2 id="idle-warning-title">Session ending soon</h2><p>You will be signed out in one minute because of inactivity.</p><button className="btn btn--primary" onClick={() => setIdleWarning(false)}>Stay signed in</button><button className="btn" onClick={logout}>Log out</button></dialog>}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider.");
  return context;
}
