import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError, mocksEnabled } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { AuthPage, type AuthFormValues } from "./AuthPage";

export function LoginRoute() {
  const { isAuthenticated, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(() => ((location.state as { expired?: boolean } | null)?.expired ? "Session expired. Sign in again to continue." : null));
  const [busy, setBusy] = useState(false);
  const destination = (location.state as { from?: string } | null)?.from ?? "/";

  if (isAuthenticated) return <Navigate to="/" replace />;

  function handleSubmit(values: AuthFormValues): void {
    setError(null);
    if (values.fullName?.trim() && values.email !== "demo@codevalidation.ai") {
      setError("Account registration is not available: the backend has no registration endpoint.");
      return;
    }
    setBusy(true);
    void login(values.email, values.password, values.remember)
      .then(() => navigate(destination, { replace: true }))
      .catch((cause: unknown) => {
        const message = cause instanceof ApiError ? cause.message : "Sign in failed. Please check your credentials and try again.";
        setError(message);
      })
      .finally(() => setBusy(false));
  }

  return (
    <>
      <AuthPage mode="signin" onModeChange={() => setError("Account registration is not available on the connected backend.")} onSubmit={handleSubmit} />
      {(error || busy || mocksEnabled()) && <div className="auth-feedback" aria-live="polite">
        {error && <p role="alert">{error}</p>}
        {busy && <p>Signing in…</p>}
        {mocksEnabled() && <p>Mock mode is enabled. Use an email beginning with “admin” to test Administrator access; other addresses receive Developer access.</p>}
      </div>}
    </>
  );
}
