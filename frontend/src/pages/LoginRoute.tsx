import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError, mocksEnabled } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { AuthPage, type AuthFormValues, type AuthMode } from "./AuthPage";

export function LoginRoute() {
  const { isAuthenticated, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(() => ((location.state as { expired?: boolean } | null)?.expired ? "Session expired. Sign in again to continue." : null));
  const [message, setMessage] = useState("");
  const [mode, setMode] = useState<AuthMode>("signin");
  const [busy, setBusy] = useState(false);
  const destination = (location.state as { from?: string } | null)?.from ?? "/";

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
      setMessage(mocksEnabled()
        ? "Demo only: no reset email was sent. The demo reset form does not change an account password."
        : "Password reset is unavailable because the connected backend has no reset endpoint. No email was sent.");
      return;
    }
    if (formMode === "reset") {
      setMessage("Demo only: the reset form was validated locally. No password was saved or changed.");
      return;
    }
    if (formMode === "signup" && !mocksEnabled()) {
      setError("Sign up is unavailable because the connected backend has no registration endpoint. No account was created.");
      return;
    }
    setBusy(true);
    void login(values.email, values.password, values.remember)
      .then(() => {
        if (formMode === "signup") setMessage("Demo mode: this is a local mock session only. No account was registered.");
        navigate(destination, { replace: true });
      })
      .catch((cause: unknown) => {
        const message = cause instanceof ApiError ? cause.message : "Sign in failed. Please check your credentials and try again.";
        setError(message);
      })
      .finally(() => setBusy(false));
  }

  return (
    <>
      <AuthPage mode={mode} mockMode={mocksEnabled()} busy={busy} message={message} error={error ?? undefined} onModeChange={handleModeChange} onSubmit={handleSubmit} />
      {(error || busy || mocksEnabled()) && <div className="auth-feedback" aria-live="polite">
        {busy && <p>Signing in…</p>}
        {mocksEnabled() && <p>Mock mode is enabled. Sign-in creates a local demo session, not a real authenticated account.</p>}
      </div>}
    </>
  );
}
