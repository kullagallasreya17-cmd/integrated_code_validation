import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { AuthPage, type AuthFormValues, type AuthMode } from "./AuthPage";

export function LoginRoute() {
  const { isAuthenticated, isLoading, login, register, loginAsLocalDemo } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(() => ((location.state as { expired?: boolean } | null)?.expired ? "Session expired. Sign in again to continue." : null));
  const [message, setMessage] = useState("");
  const [mode, setMode] = useState<AuthMode>("signin");
  const [busy, setBusy] = useState(false);
  const destination = (location.state as { from?: string } | null)?.from ?? "/";
  const localDemoEnabled = import.meta.env.VITE_LOCAL_DEMO_AUTH === "true";

  if (isLoading) return <main className="auth-loading" aria-live="polite">Checking your session…</main>;
  if (isAuthenticated) return <Navigate to="/" replace />;

  function handleModeChange(nextMode: AuthMode): void {
    setError(null);
    setMessage("");
    setMode(nextMode);
  }

  function handleSubmit(values: AuthFormValues, formMode: AuthMode): void {
    setError(null);
    setMessage("");
    if (formMode === "forgot") {
      setMessage("Password recovery is not configured. Contact your administrator; no email was sent.");
      return;
    }
    if (formMode === "reset") {
      setMessage("Password reset is not configured; no password was changed.");
      return;
    }
    setBusy(true);
    const request = formMode === "signup"
      ? register(values.fullName ?? "", values.email, values.password)
      : login(values.email, values.password, values.remember);
    void request
      .then(() => {
        navigate(destination, { replace: true });
      })
      .catch((cause: unknown) => {
        setError(cause instanceof ApiError ? cause.message : "Sign in failed. Please check your credentials and try again.");
      })
      .finally(() => setBusy(false));
  }

  function handleLocalDemo(): void {
    setBusy(true);
    setError(null);
    void loginAsLocalDemo()
      .then(() => navigate(destination, { replace: true }))
      .catch((cause: unknown) => setError(cause instanceof ApiError ? cause.message : "Local demo access is unavailable."))
      .finally(() => setBusy(false));
  }

  return (
    <>
      <AuthPage mode={mode} localDemoEnabled={localDemoEnabled} busy={busy} message={message} error={error ?? undefined} onModeChange={handleModeChange} onSubmit={handleSubmit} onLocalDemo={handleLocalDemo} />
      {(error || busy) && <div className="auth-feedback" aria-live="polite">
        {busy && <p>Signing in…</p>}
      </div>}
    </>
  );
}
