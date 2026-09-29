import { useState } from "react";

export type AuthFormValues = {
  fullName?: string;
  email: string;
  password: string;
  remember: boolean;
};

interface AuthPageProps {
  mode: "signin" | "signup";
  onModeChange: (mode: "signin" | "signup") => void;
  onSubmit: (values: AuthFormValues) => void;
}

export function AuthPage({ mode, onModeChange, onSubmit }: Readonly<AuthPageProps>) {
  const isSignup = mode === "signup";
  const [showPassword, setShowPassword] = useState(false);
  const [form, setForm] = useState<AuthFormValues>({
    fullName: "",
    email: "",
    password: "",
    remember: true,
  });

  function handleFieldChange(key: keyof AuthFormValues, value: string | boolean) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!form.email.trim() || !form.password.trim()) {
      return;
    }

    if (isSignup && !form.fullName?.trim()) {
      return;
    }

    onSubmit({
      ...form,
      email: form.email.trim(),
      fullName: form.fullName?.trim(),
    });
  }

  return (
    <div className="auth-shell auth-shell--reference">
      <header className="auth-nav">
        <div className="auth-nav__brand"><span className="auth-nav__logo">&lt;/&gt;</span><strong>Code Validation Agent</strong></div>
      </header>

      <div className="auth-reference-layout" id="home">
        <section className="auth-reference-hero">
          <p className="reference-eyebrow">AI-POWERED ENGINEERING WORKSPACE</p>
          <h1>AI-Powered Code<br /><em>Validation &amp; Repair</em><br />for Safer, Cleaner Code</h1>
          <p className="auth-intro">Analyze your Python code, detect issues, get intelligent fixes, and keep your code secure, reliable, and maintainable — all in one place.</p>

          <ul className="feature-list">
            <li><span className="feature-list__icon">01</span><span><strong>Multi-Agent Validation</strong><small>Code quality, security, bugs, and more.</small></span></li>
            <li><span className="feature-list__icon">02</span><span><strong>AI-Powered Repair</strong><small>Get intelligent fixes and re-validate your code.</small></span></li>
            <li><span className="feature-list__icon">03</span><span><strong>Clear Insights</strong><small>Detailed reports, history, and recommendations.</small></span></li>
            <li><span className="feature-list__icon">04</span><span><strong>Secure &amp; Reliable</strong><small>Sandboxed execution and safe analysis.</small></span></li>
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
            <div className="agent-badge agent-badge--orchestrator"><span className="agent-badge__index">ORCH</span><span>Orchestrator Agent</span></div>
            <div className="agent-badge agent-badge--code-analysis"><span className="agent-badge__index">01</span><span>Code Analysis</span></div>
            <div className="agent-badge agent-badge--security"><span className="agent-badge__index">02</span><span>Security</span></div>
            <div className="agent-badge agent-badge--quality"><span className="agent-badge__index">03</span><span>Code Quality</span></div>
            <div className="agent-badge agent-badge--bug"><span className="agent-badge__index">04</span><span>Bug &amp; Resource</span></div>
            <div className="agent-badge agent-badge--repair"><span className="agent-badge__index">05</span><span>Fix &amp; Regeneration</span></div>
            <div className="agent-badge agent-badge--validation"><span className="agent-badge__index">06</span><span>Validation</span></div>
            <div className="agent-badge agent-badge--report"><span className="agent-badge__index">07</span><span>Report &amp; Recommendation</span></div>
          </div>

        </section>

        <section className="auth-card auth-card--reference auth-card__panel--form">
          <div className="auth-form__logo">&lt;/&gt;</div>
          <h2>{isSignup ? "Create your workspace" : "Welcome Back"}</h2>
          <p className="auth-form__intro">{isSignup ? "Start validating and improving your code today" : "Sign in to your Code Validation Agent account"}</p>
          <form className="auth-form" onSubmit={handleSubmit}>
            {isSignup && (
              <label className="field">
                <span>Full name</span>
                <input
                  type="text"
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
                placeholder="name@company.com"
                value={form.email}
                onChange={(event) => handleFieldChange("email", event.target.value)}
              />
            </label>

            <label className="field">
              <span>Password</span>
              <span className="field__input-wrap">
                <input
                  type={showPassword ? "text" : "password"}
                  placeholder={isSignup ? "Create a strong password" : "Enter your password"}
                  value={form.password}
                  onChange={(event) => handleFieldChange("password", event.target.value)}
                />
                <button type="button" className="field__visibility" onClick={() => setShowPassword((visible) => !visible)} aria-label={showPassword ? "Hide password" : "Show password"}>
                  {showPassword ? "Hide" : "Show"}
                </button>
              </span>
            </label>

            <div className="auth-row">
              <label className="remember-me">
                <input
                  type="checkbox"
                  checked={form.remember}
                  onChange={(event) => handleFieldChange("remember", event.target.checked)}
                />
                <span>Keep me signed in</span>
              </label>
              {!isSignup && <button type="button" className="inline-link">Forgot password?</button>}
            </div>

            <button type="submit" className="btn btn--primary auth-submit">
              {isSignup ? "Create Account" : "Sign In"}<span>→</span>
            </button>

            <div className="auth-divider"><span>or</span></div>
            <button type="button" className="btn btn--secondary auth-demo" onClick={() => onSubmit({ fullName: "Demo Analyst", email: "demo@codevalidation.ai", password: "demo123", remember: true })}><span className="google-mark">G</span> Continue with Google</button>
            <p className="auth-switch">{isSignup ? "Already have an account?" : "Don't have an account?"} <button type="button" className="inline-link" onClick={() => onModeChange(isSignup ? "signin" : "signup")}>{isSignup ? "Sign In" : "Sign Up"}</button></p>
          </form>
        </section>
      </div>
      <div className="auth-shell__wave" />
    </div>
  );
}
