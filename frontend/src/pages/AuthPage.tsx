import { useState } from "react";

export type AuthMode = "signin" | "signup" | "forgot" | "reset";

export type AuthFormValues = {
  fullName?: string;
  email: string;
  password: string;
  confirmPassword?: string;
  resetToken?: string;
  remember: boolean;
};

interface AuthPageProps {
  readonly mode: AuthMode;
  readonly mockMode: boolean;
  readonly busy: boolean;
  readonly message?: string;
  readonly error?: string;
  readonly onModeChange: (mode: AuthMode) => void;
  readonly onSubmit: (values: AuthFormValues, mode: AuthMode) => void;
}

function headingForMode(mode: AuthMode): string {
  const headings: Record<AuthMode, string> = {
    signin: "Welcome Back",
    signup: "Create your workspace",
    forgot: "Forgot password",
    reset: "Reset password",
  };
  return headings[mode];
}

function introForMode(mode: AuthMode, mockMode: boolean): string {
  if (mode === "forgot") return mockMode ? "Demo mode only. No reset email will be sent." : "Password reset is unavailable until the authentication service is connected.";
  if (mode === "reset") return mockMode ? "Demo mode only. The new password will not be saved." : "Password reset is unavailable until the authentication service is connected.";
  if (mode === "signup") return mockMode ? "Demo account only. No account will be registered." : "Registration is unavailable until the authentication service is connected.";
  return "Sign in to your Code Validation Agent account";
}

export function AuthPage({ mode, mockMode, busy, message, error, onModeChange, onSubmit }: Readonly<AuthPageProps>) {
  const isSignup = mode === "signup";
  const isRecovery = mode === "forgot" || mode === "reset";
  const [showPassword, setShowPassword] = useState(false);
  const [form, setForm] = useState<AuthFormValues>({
    fullName: "",
    email: "",
    password: "",
    confirmPassword: "",
    resetToken: "",
    remember: true,
  });
  const [formError, setFormError] = useState("");

  function handleFieldChange(key: keyof AuthFormValues, value: string | boolean) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");

    if (!form.email.trim()) {
      setFormError("Enter a valid email address.");
      return;
    }

    if (isSignup && !form.fullName?.trim()) {
      setFormError("Enter your full name.");
      return;
    }

    if ((isSignup || mode === "reset") && form.password.length < 8) {
      setFormError("Use a password with at least 8 characters.");
      return;
    }

    if (mode === "reset" && !form.resetToken?.trim()) {
      setFormError("Enter the reset token supplied by your authentication service.");
      return;
    }

    if ((isSignup || mode === "reset") && form.password !== form.confirmPassword) {
      setFormError("The passwords do not match.");
      return;
    }

    if (!isRecovery && !form.password.trim()) {
      setFormError("Enter your password.");
      return;
    }

    onSubmit({
      ...form,
      email: form.email.trim(),
      fullName: form.fullName?.trim(),
    }, mode);
  }

  return (
    <div className="auth-shell auth-shell--reference">
      <header className="auth-nav">
        <div className="auth-nav__brand"><span className="auth-nav__logo">&lt;/&gt;</span><strong>Code Validation Agent</strong></div>
      </header>

      <div className="auth-reference-layout" id="home">
        <section className="auth-reference-hero">
          <p className="reference-eyebrow">PYTHON ANALYSIS WORKSPACE</p>
          <h1>Python code checks<br /><em>with reviewable evidence</em></h1>
          <p className="auth-intro">Run static quality checks, follow the orchestrated workflow, and review findings from the services connected to this deployment.</p>

          <ul className="feature-list">
            <li><span className="feature-list__icon">01</span><span><strong>Static quality checks</strong><small>Ruff, Pylint, and Radon in one run.</small></span></li>
            <li><span className="feature-list__icon">02</span><span><strong>Workflow visibility</strong><small>Follow orchestrator stages and outcomes.</small></span></li>
            <li><span className="feature-list__icon">03</span><span><strong>Reviewable findings</strong><small>Inspect severity, source locations, and tool evidence.</small></span></li>
            <li><span className="feature-list__icon">04</span><span><strong>Clear integration status</strong><small>See which agents are connected or not deployed.</small></span></li>
          </ul>

          <div className="auth-illustration" aria-label="Code analysis workflow illustration">
            <svg className="auth-illustration__connections" viewBox="0 0 560 500" aria-hidden="true">
              <path className="connection-line" d="M280 44 C280 83 280 120 280 160" />
              <path className="connection-line" d="M160 87 C181 104 193 131 205 160" />
              <path className="connection-line" d="M400 87 C379 104 367 131 355 160" />
              <path className="connection-line" d="M160 232 C164 232 167 232 170 232" />
              <path className="connection-line" d="M400 232 C396 232 393 232 390 232" />
              <path className="connection-line" d="M160 423 C181 406 193 369 205 340" />
              <path className="connection-line" d="M400 423 C379 406 367 369 355 340" />
              <path className="connection-line" d="M280 456 C280 416 280 378 280 340" />
              <circle className="connection-node" cx="280" cy="160" r="3" />
              <circle className="connection-node" cx="205" cy="160" r="3" />
              <circle className="connection-node" cx="355" cy="160" r="3" />
              <circle className="connection-node" cx="170" cy="232" r="3" />
              <circle className="connection-node" cx="390" cy="232" r="3" />
              <circle className="connection-node" cx="205" cy="340" r="3" />
              <circle className="connection-node" cx="355" cy="340" r="3" />
              <circle className="connection-node" cx="280" cy="340" r="3" />
            </svg>
            <div className="code-window">
              <div className="code-window__bar"><i /><i /><i /><b>Python</b></div>
              <pre>
                <span className="code-window__line"><span>1</span><em>def</em> calculate_total(items):</span>
                <span className="code-window__line"><span>2</span>    total = <strong>0</strong></span>
                <span className="code-window__line"><span>3</span>    <em>for</em> item <em>in</em> items:</span>
                <span className="code-window__line"><span>4</span>        total += item.price</span>
                <span className="code-window__line"><span>5</span></span>
                <span className="code-window__line"><span>6</span>    <em>return</em> total</span>
              </pre>
            </div>
            <div className="agent-badge agent-badge--orchestrator"><span className="agent-badge__index">ORCH</span><span>Workflow</span></div>
            <div className="agent-badge agent-badge--code-analysis"><span className="agent-badge__index">ON</span><span>Code Analysis</span></div>
            <div className="agent-badge agent-badge--security"><span className="agent-badge__index">OFF</span><span>Security</span></div>
            <div className="agent-badge agent-badge--quality"><span className="agent-badge__index">ON</span><span>Code Quality</span></div>
            <div className="agent-badge agent-badge--bug"><span className="agent-badge__index">OFF</span><span>Bug &amp; Resource</span></div>
            <div className="agent-badge agent-badge--repair"><span className="agent-badge__index">OFF</span><span>Repair</span></div>
            <div className="agent-badge agent-badge--validation"><span className="agent-badge__index">OFF</span><span>Validation</span></div>
            <div className="agent-badge agent-badge--report"><span className="agent-badge__index">STAGE</span><span>Reporting</span></div>
          </div>

        </section>

        <section className="auth-card auth-card--reference auth-card__panel--form">
          <div className="auth-form__logo">&lt;/&gt;</div>
          <h2>{headingForMode(mode)}</h2>
          <p className="auth-form__intro">{introForMode(mode, mockMode)}</p>
          {mockMode && <p className="auth-demo-notice">DEMO MODE · Credentials and reset flows are local demonstrations only.</p>}
          {error && <p className="auth-feedback-message" role="alert">{error}</p>}
          {formError && <p className="auth-feedback-message" role="alert">{formError}</p>}
          {message && <output className="auth-feedback-message">{message}</output>}
          <form className="auth-form" onSubmit={handleSubmit}>
            {isSignup && (
              <label className="field">
                <span>Full name</span>
                <input
                  type="text"
                  required
                  placeholder="Alex Morgan"
                  value={form.fullName ?? ""}
                  onChange={(event) => handleFieldChange("fullName", event.target.value)}
                />
              </label>
            )}

            <label className="field">
              <span>Email address</span>
              <input
                type="email"
                required
                placeholder="name@company.com"
                value={form.email}
                onChange={(event) => handleFieldChange("email", event.target.value)}
              />
            </label>

            {mode === "reset" && <label className="field"><span>Reset token</span><input type="text" required autoComplete="one-time-code" value={form.resetToken ?? ""} onChange={(event) => handleFieldChange("resetToken", event.target.value)} /></label>}

            {mode !== "forgot" && <label className="field">
              <span>Password</span>
              <span className="field__input-wrap">
                <input
                  type={showPassword ? "text" : "password"}
                  placeholder={isSignup ? "Create a strong password" : "Enter your password"}
                  required
                  minLength={isSignup || mode === "reset" ? 8 : undefined}
                  autoComplete={mode === "signin" ? "current-password" : "new-password"}
                  value={form.password}
                  onChange={(event) => handleFieldChange("password", event.target.value)}
                />
                <button type="button" className="field__visibility" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? "Hide password" : "Show password"}>
                  {showPassword ? "Hide" : "Show"}
                </button>
              </span>
            </label>}

            {(isSignup || mode === "reset") && <label className="field"><span>Confirm password</span><input type="password" required minLength={8} autoComplete="new-password" value={form.confirmPassword ?? ""} onChange={(event) => handleFieldChange("confirmPassword", event.target.value)} /></label>}

            {mode === "signin" && <div className="auth-row">
              <label className="remember-me">
                <input
                  type="checkbox"
                  checked={form.remember}
                  onChange={(event) => handleFieldChange("remember", event.target.checked)}
                />
                <span>Keep me signed in</span>
              </label>
              <button type="button" className="inline-link" onClick={() => onModeChange("forgot")}>Forgot password?</button>
            </div>}

            <button type="submit" className="btn btn--primary auth-submit" disabled={busy || (!mockMode && isRecovery)}>
              {busy ? "Please wait..." : submitLabel(mode)}{!busy && <span>→</span>}
            </button>

            {mode === "signin" && mockMode && <><div className="auth-divider"><span>or</span></div><button type="button" className="btn btn--secondary auth-demo" disabled={busy} onClick={() => onSubmit({ fullName: "Demo Analyst", email: "demo@codevalidation.ai", password: "demo123", remember: true }, "signin")}>Use demo account</button></>}
            {mode === "signin" && <p className="auth-switch">Don't have an account? <button type="button" className="inline-link" onClick={() => onModeChange("signup")}>Sign Up</button></p>}
            {mode === "signup" && <p className="auth-switch">Already have an account? <button type="button" className="inline-link" onClick={() => onModeChange("signin")}>Sign In</button></p>}
            {mode === "forgot" && mockMode && <button type="button" className="btn btn--secondary auth-demo" onClick={() => onModeChange("reset")}>Open demo reset form</button>}
            {isRecovery && <p className="auth-switch"><button type="button" className="inline-link" onClick={() => onModeChange("signin")}>Back to Sign In</button></p>}
          </form>
        </section>
      </div>
      <div className="auth-shell__wave" />
    </div>
  );
}

function submitLabel(mode: AuthMode): string {
  const labels: Record<AuthMode, string> = {
    signin: "Sign In",
    signup: "Create demo account",
    forgot: "Request password reset",
    reset: "Reset password",
  };
  return labels[mode];
}
