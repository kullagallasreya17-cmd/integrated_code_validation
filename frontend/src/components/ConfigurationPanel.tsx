import { useEffect, useState } from "react";
import { getAdminConfiguration, saveAdminConfiguration, testLlmConnection, validateAnalysisConfiguration, type AnalysisConfiguration, type LlmProvider, DEFAULT_ANALYSIS_CONFIGURATION } from "../api/configuration";

interface ConfigurationPanelProps {
  readonly mode: "analysis" | "admin";
  readonly onChange?: (configuration: AnalysisConfiguration) => void;
}

const PROVIDERS: LlmProvider[] = ["Ollama", "OpenAI", "Claude", "Gemini"];

function connectionLabel(value: "unchecked" | "connected" | "unreachable"): string {
  if (value === "connected") return "Connected";
  if (value === "unreachable") return "Unreachable";
  return "Not tested";
}

export function ConfigurationPanel({ mode, onChange }: Readonly<ConfigurationPanelProps>) {
  const [configuration, setConfiguration] = useState<AnalysisConfiguration>(DEFAULT_ANALYSIS_CONFIGURATION);
  const [apiKey, setApiKey] = useState("");
  const [apiKeyConfigured, setApiKeyConfigured] = useState(false);
  const [connection, setConnection] = useState<"unchecked" | "connected" | "unreachable">("unchecked");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(mode === "admin");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (mode !== "admin") return undefined;
    const controller = new AbortController();
    void getAdminConfiguration(controller.signal).then((saved) => {
      const next: AnalysisConfiguration = {
        sandbox_timeout_seconds: saved.sandbox_timeout_seconds ?? DEFAULT_ANALYSIS_CONFIGURATION.sandbox_timeout_seconds,
        memory_limit_mb: saved.memory_limit_mb ?? DEFAULT_ANALYSIS_CONFIGURATION.memory_limit_mb,
        cpu_limit: saved.cpu_limit ?? DEFAULT_ANALYSIS_CONFIGURATION.cpu_limit,
        network_policy: saved.network_policy ?? DEFAULT_ANALYSIS_CONFIGURATION.network_policy,
        llm_provider: saved.llm_provider ?? DEFAULT_ANALYSIS_CONFIGURATION.llm_provider,
        model_name: saved.model_name ?? DEFAULT_ANALYSIS_CONFIGURATION.model_name,
      };
      setConfiguration(next); setApiKeyConfigured(Boolean(saved.api_key_configured)); onChange?.(next);
    }).catch((error: unknown) => { if (!controller.signal.aborted) setMessage(error instanceof Error ? error.message : "Configuration could not be loaded."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [mode, onChange]);

  function update<K extends keyof AnalysisConfiguration>(key: K, value: AnalysisConfiguration[K]) {
    const next = { ...configuration, [key]: value };
    setConfiguration(next); setConnection("unchecked"); onChange?.(next);
  }

  async function testConnection() {
    setBusy(true); setMessage("");
    try {
      const result = await testLlmConnection(configuration.llm_provider, configuration.model_name, apiKey || undefined);
      setConnection(result.reachable ? "connected" : "unreachable"); setMessage(result.reachable ? "Connection available." : "Provider is unreachable.");
      setApiKey("");
    } catch (error) { setConnection("unreachable"); setMessage(error instanceof Error ? error.message : "Connection test failed."); setApiKey(""); }
    finally { setBusy(false); }
  }

  async function save() {
    if (!validateAnalysisConfiguration(configuration)) { setMessage("Check the supported timeout, memory, CPU, and model values."); return; }
    setBusy(true); setMessage("");
    try {
      await saveAdminConfiguration(configuration, apiKey || undefined);
      setApiKey(""); setApiKeyConfigured(apiKeyConfigured || Boolean(apiKey)); setMessage("Settings saved. API keys are write-only and are not returned.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Settings could not be saved."); }
    finally { setBusy(false); }
  }

  if (loading) return <p aria-live="polite">Loading settings...</p>;
  return <fieldset className="configuration-panel"><legend>{mode === "admin" ? "Sandbox and LLM settings" : "Analysis options"}</legend>
    <div className="configuration-grid">
      <label>Sandbox timeout (seconds)<input type="number" min="1" max="600" step="1" value={configuration.sandbox_timeout_seconds} onChange={(event) => update("sandbox_timeout_seconds", Number(event.target.value))} /></label>
      <label>Memory limit (MB)<input type="number" min="64" max="8192" step="64" value={configuration.memory_limit_mb} onChange={(event) => update("memory_limit_mb", Number(event.target.value))} /></label>
      <label>CPU limit (cores)<input type="number" min="0.1" max="8" step="0.1" value={configuration.cpu_limit} onChange={(event) => update("cpu_limit", Number(event.target.value))} /></label>
      <label>Network policy<select value={configuration.network_policy} onChange={(event) => update("network_policy", event.target.value as AnalysisConfiguration["network_policy"])}><option value="restricted">Restricted</option><option value="off">Off</option></select></label>
      <label>LLM provider<select value={configuration.llm_provider} onChange={(event) => update("llm_provider", event.target.value as LlmProvider)}>{PROVIDERS.map((provider) => <option key={provider}>{provider}</option>)}</select></label>
      <label>Model name<input value={configuration.model_name} onChange={(event) => update("model_name", event.target.value)} maxLength={120} /></label>
      <label className="configuration-secret">API key <input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} autoComplete="new-password" placeholder={apiKeyConfigured ? "Configured; enter a new key to replace" : "Write-only; never displayed again"} /></label>
    </div>
    <div className="configuration-actions"><button className="btn" disabled={busy || !validateAnalysisConfiguration(configuration)} onClick={() => void testConnection()}>{busy ? "Working..." : "Test connection"}</button>{mode === "admin" && <button className="btn btn--primary" disabled={busy || !validateAnalysisConfiguration(configuration)} onClick={() => void save()}>Save settings</button>}<span className={`connection-badge connection-badge--${connection}`}>{connectionLabel(connection)}</span></div>
    {mode === "admin" && <p>Current key: {apiKeyConfigured ? "Configured" : "Not configured"}. Secret values cannot be read back.</p>}
    {message && <output aria-live="polite">{message}</output>}
  </fieldset>;
}