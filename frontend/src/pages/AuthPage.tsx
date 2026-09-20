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

export function AuthPage({ mode, onModeChange, onSubmit }: AuthPageProps) {
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
            <li><span className="feature-list__icon feature-list__icon--purple">✧</span><span><strong>Multi-Agent Validation</strong><small>Code quality, security, bugs, and more.</small></span></li>
            <li><span className="feature-list__icon feature-list__icon--blue">ϟ</span><span><strong>AI-Powered Repair</strong><small>Get intelligent fixes and re-validate your code.</small></span></li>
            <li><span className="feature-list__icon feature-list__icon--green">▥</span><span><strong>Clear Insights</strong><small>Detailed reports, history, and recommendations.</small></span></li>
            <li><span className="feature-list__icon feature-list__icon--orange">▣</span><span><strong>Secure &amp; Reliable</strong><small>Sandboxed execution and safe analysis.</small></span></li>
          </ul>

          <div className="auth-illustration" aria-label="Code analysis workflow illustration">
            <svg className="auth-illustration__connections" viewBox="0 0 350 300" aria-hidden="true">
              <path className="connection-line connection-line--green" d="M105 48 C116 43 125 42 139 52" />
              <path className="connection-line connection-line--purple" d="M325 76 C331 68 337 61 344 55" />
              <path className="connection-line connection-line--red" d="M103 135 C80 135 57 143 35 148" />
              <path className="connection-line connection-line--blue" d="M153 194 C142 216 127 235 108 253" />
              <path className="connection-line connection-line--purple" d="M285 194 C298 213 311 228 327 242" />
              <circle className="connection-node connection-node--green" cx="139" cy="52" r="3" />
              <circle className="connection-node connection-node--purple" cx="325" cy="76" r="3" />
              <circle className="connection-node connection-node--red" cx="103" cy="135" r="3" />
              <circle className="connection-node connection-node--blue" cx="153" cy="194" r="3" />
              <circle className="connection-node connection-node--purple" cx="285" cy="194" r="3" />
            </svg>
            <div className="code-window"><div className="code-window__bar"><i /><i /><i /><b>Python</b></div><pre><span>1</span> <em>def</em> calculate_total(items):
<span>2</span>     total = <strong>0</strong>
<span>3</span>     <em>for</em> item <em>in</em> items:
<span>4</span>         total += item.price
<span>5</span>
<span>6</span>     <em>return</em> total</pre></div>
            <div className="agent-badge agent-badge--security">◈ <span>Security<br /><b>Analysis</b></span></div>
            <div className="agent-badge agent-badge--quality">✦ <span>Code Quality<br /><b>(Ruff / Pylint / Radon)</b></span></div>
            <div className="agent-badge agent-badge--bug">✹ <span>Bug &amp; Resource<br /><b>Detection</b></span></div>
            <div className="agent-badge agent-badge--repair">⌕ <span>Auto Repair<br /><b>&amp; Validation</b></span></div>
            <div className="agent-badge agent-badge--report">▤ <span>Final Report</span></div>
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
