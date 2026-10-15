import { FileUpload } from "../components/FileUpload";
import { useEffect, useState } from "react";
import { CodeEditor } from "../components/CodeEditor";
import type { ProjectFile, QualityTool, RunHistoryEntry } from "../types/finding";
import { DEFAULT_ANALYSIS_CHECKS, type AnalysisCheckOptions } from "../api/configuration";
import { validatePythonPath } from "../api/files";
import { apiClient } from "../api/client";

interface UploadPageProps {
  onStart: (files: ProjectFile[], tools: QualityTool[], projectName?: string, existingProjectId?: string, checks?: AnalysisCheckOptions) => Promise<void>;
  history: RunHistoryEntry[];
  onOpenHistory: (entry: RunHistoryEntry) => void;
  initialFiles?: ProjectFile[];
  initialProjectName?: string;
  existingProjectId?: string;
  projectLoadError?: string;
  runInProgress?: boolean;
}

const TOOL_OPTIONS: QualityTool[] = ["ruff", "pylint", "radon"];
const TOOL_DESCRIPTION: Record<QualityTool, string> = {
  ruff: "Fast Python linting and style analysis",
  pylint: "Python code quality and maintainability analysis",
  radon: "Python complexity analysis",
};

interface AgentHealth {
  readonly status: string;
  readonly healthy: boolean;
}

const CHECK_OPTIONS: Array<{ key: keyof AnalysisCheckOptions; title: string; description: string }> = [
  { key: "codeQuality", title: "Code Quality", description: "Run Ruff and Pylint against Python files." },
  { key: "security", title: "Security", description: "Run security scanners against Python files." },
  { key: "bugResource", title: "Bug & Resource Analysis", description: "Detect bug and resource-use risks in Python files." },
  { key: "complexity", title: "Complexity Analysis", description: "Run Radon to identify complexity hotspots." },
  { key: "automatedRepair", title: "Automated Repair", description: "Generate a repair candidate with the configured Ollama model, then validate it." },
  { key: "finalValidation", title: "Final Validation", description: "Run the sandbox and Python validation service on the submitted or repaired code." },
  { key: "aiReportRecommendations", title: "AI Report & Recommendations", description: "Send source code to the configured Gemini model for an additional review and proposed fixes." },
];

function describeAgentAvailability(
  services: Record<string, AgentHealth> | null,
  service: AgentHealth | undefined,
  description: string,
): string {
  if (service?.healthy) return description;
  if (!services) return "Checking agent availability...";
  if (!service) return "Agent availability could not be checked.";
  if (service.status === "not_configured") return "Not available in this deployment.";
  return "Service is currently unavailable.";
}

function buildCheckOptions(services: Record<string, AgentHealth> | null) {
  return CHECK_OPTIONS.map((option) => {
    let serviceKey: string | undefined;
    if (option.key === "security") serviceKey = "security";
    if (option.key === "bugResource") serviceKey = "bug_resource";
    if (!serviceKey) return { ...option, available: true };

    const service = services?.[serviceKey];
    return {
      ...option,
      available: service?.healthy === true,
      description: describeAgentAvailability(services, service, option.description),
    };
  });
}

function checkMarker(selected: boolean, available: boolean): string {
  if (selected) return "✓";
  if (!available) return "–";
  return "";
}

function qualityToolStatus(configured: boolean, selected: boolean): string {
  if (configured) return "Configured";
  if (selected) return "Disabled by check";
  return "Not selected";
}

function AnalysisPresetControl({ preset, onRecommended, onCustom }: Readonly<{
  preset: "recommended" | "custom";
  onRecommended: () => void;
  onCustom: () => void;
}>) {
  return <fieldset className="analysis-presets" aria-label="Analysis preset"><legend>Analysis preset</legend><button type="button" className={preset === "recommended" ? "analysis-preset analysis-preset--active" : "analysis-preset"} onClick={onRecommended}>Recommended</button><button type="button" className={preset === "custom" ? "analysis-preset analysis-preset--active" : "analysis-preset"} onClick={onCustom}>Custom</button></fieldset>;
}

function AnalysisCheckCards({ options, checks, onChange }: Readonly<{
  options: ReturnType<typeof buildCheckOptions>;
  checks: AnalysisCheckOptions;
  onChange: <K extends keyof AnalysisCheckOptions>(key: K, value: AnalysisCheckOptions[K]) => void;
}>) {
  return <div className="analysis-check-grid">{options.map(({ key, title, description, available }) => <label className={`analysis-check-card${checks[key] ? " analysis-check-card--selected" : ""}${available ? "" : " analysis-check-card--unavailable"}`} key={key}><input type="checkbox" checked={checks[key]} disabled={!available} onChange={(event) => onChange(key, event.target.checked)} /><span className="analysis-check-card__mark" aria-hidden="true">{checkMarker(checks[key], available)}</span><span><strong>{title}</strong><small>{description}</small>{!available && <b>Unavailable</b>}</span></label>)}</div>;
}

function AnalysisCheckWarnings({ checks, activeChecks }: Readonly<{ checks: AnalysisCheckOptions; activeChecks: AnalysisCheckOptions }>) {
  return <>
    {checks.codeQuality && !activeChecks.codeQuality && <output className="inline-error">Select Ruff or Pylint to run Code Quality analysis.</output>}
    {checks.complexity && !activeChecks.complexity && <output className="inline-error">Select Radon to run Complexity Analysis.</output>}
  </>;
}

function QualityToolCards({ tools, selectedTools, onChange }: Readonly<{
  tools: QualityTool[];
  selectedTools: QualityTool[];
  onChange: (tool: QualityTool, selected: boolean) => void;
}>) {
  return <div className="quality-tool-grid">{TOOL_OPTIONS.map((tool) => {
    const configured = selectedTools.includes(tool);
    const selected = tools.includes(tool);
    const className = selected ? "quality-tool-card quality-tool-card--selected" : "quality-tool-card";
    return <label key={tool} className={className}><input type="checkbox" checked={selected} onChange={(event) => onChange(tool, event.target.checked)} /><span className="quality-tool-card__mark" aria-hidden="true">{selected ? "✓" : ""}</span><span><strong>{tool[0].toUpperCase() + tool.slice(1)}</strong><small>{TOOL_DESCRIPTION[tool]}</small></span><b>{qualityToolStatus(configured, selected)}</b></label>;
  })}</div>;
}

function UploadInputMethod({ inputMode, onInputModeChange, onFilesReady, code, onCodeChange, filename, onFilenameChange, validPath }: Readonly<{
  inputMode: "files" | "code";
  onInputModeChange: (mode: "files" | "code") => void;
  onFilesReady: (files: ProjectFile[]) => void;
  code: string;
  onCodeChange: (value: string) => void;
  filename: string;
  onFilenameChange: (value: string) => void;
  validPath: string;
}>) {
  return <>
    <fieldset className="input-tabs" aria-label="Code input method">
      <button type="button" aria-pressed={inputMode === "files"} className={inputMode === "files" ? "input-tab input-tab--active" : "input-tab"} onClick={() => onInputModeChange("files")}>Project files <small>UPLOAD</small></button>
      <button type="button" aria-pressed={inputMode === "code"} className={inputMode === "code" ? "input-tab input-tab--active" : "input-tab"} onClick={() => onInputModeChange("code")}>Quick code <small>PASTE</small></button>
    </fieldset>
    {inputMode === "files" ? <FileUpload onFilesReady={onFilesReady} /> : <div className="code-entry">
      <div className="code-entry__bar"><span className="window-dots"><i /><i /><i /></span><label className="code-entry__filename">Filename<input aria-label="Filename for pasted Python code" value={filename} maxLength={180} onChange={(event) => onFilenameChange(event.target.value)} /></label><span className="code-entry__meta">Python 3.11</span></div>
      <CodeEditor path={validPath || "pasted-code.py"} value={code} onChange={onCodeChange} height="250px" />
      {!validPath && <p className="inline-error" role="alert">Enter a relative Python filename ending in .py. Paths cannot be absolute or contain '..'.</p>}
    </div>}
  </>;
}

function AnalysisSummary({ checks, tools }: Readonly<{ checks: AnalysisCheckOptions; tools: QualityTool[] }>) {
  const checkLabels: Array<[boolean, string]> = [
    [checks.codeQuality, "Code Quality"],
    [checks.security, "Security"],
    [checks.bugResource, "Bugs & Resources"],
    [checks.complexity, "Complexity"],
    [checks.automatedRepair, "Repair"],
    [checks.finalValidation, "Validation"],
    [checks.aiReportRecommendations, "AI Report & Recommendations"],
  ];
  const selectedChecks = checkLabels.filter(([selected]) => selected).map(([, label]) => label).join(" · ") || "No checks selected";
  const selectedTools = tools.map((tool) => tool[0].toUpperCase() + tool.slice(1)).join(" · ") || "None selected";
  return <section className="validation-summary" aria-label="Analysis summary">
    <div><p className="kicker">READY TO RUN</p><h2>Analysis Summary</h2></div>
    <div><span>Checks</span><p>{selectedChecks}</p></div>
    <div><span>Tools</span><p>{selectedTools}</p></div>
    <div><span>Execution</span><p>Backend-managed; per-analysis sandbox limits unavailable</p></div>
  </section>;
}

function StartAnalysisControls({ disabled, submitting, runInProgress, error, onStart }: Readonly<{
  disabled: boolean;
  submitting: boolean;
  runInProgress: boolean;
  error: string;
  onStart: () => void;
}>) {
  return <>
    <button className="btn btn--primary" disabled={disabled} onClick={onStart}>{submitting ? "Analysis running..." : "Start Analysis"} {!submitting && <span>→</span>}</button>
    {(submitting || runInProgress) && <p className="analysis-pulse" role="status" aria-live="polite">Running the selected analysis checks...</p>}
    {error && <p className="inline-error" role="alert">{error}</p>}
  </>;
}

function RecentRuns({ history, onOpenHistory }: Readonly<{ history: RunHistoryEntry[]; onOpenHistory: (entry: RunHistoryEntry) => void }>) {
  if (history.length === 0) return null;
  return <section className="past-runs">
    <div className="section-label"><h2>Recent runs</h2><span>{history.length} saved locally</span></div>
    <ul className="history-list">{history.map((entry) => <li key={`${entry.project_id}-${entry.timestamp}`}>
      <button className="btn btn--link" onClick={() => onOpenHistory(entry)}>
        <span className="history-list__icon">↗</span><span><strong>{entry.project_id}</strong><small>{new Date(entry.timestamp).toLocaleString()}</small></span><b className={`status-pill status-pill--${entry.validation_status}`}>{entry.validation_status}</b>
      </button>
    </li>)}</ul>
  </section>;
}

export function UploadPage({ onStart, history, onOpenHistory, initialFiles = [], initialProjectName, existingProjectId, projectLoadError, runInProgress = false }: Readonly<UploadPageProps>) {
  const [files, setFiles] = useState<ProjectFile[]>(initialFiles);
  const [projectName, setProjectName] = useState(initialProjectName ?? "Python project");
  const [checks, setChecks] = useState(DEFAULT_ANALYSIS_CHECKS);
  const [preset, setPreset] = useState<"recommended" | "custom">("recommended");
  const [tools, setTools] = useState<QualityTool[]>(TOOL_OPTIONS);
  const [inputMode, setInputMode] = useState<"files" | "code">("files");
  const [code, setCode] = useState("def example(value):\n    return value\n");
  const [pastedFilename, setPastedFilename] = useState("pasted-code.py");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [agentServices, setAgentServices] = useState<Record<string, AgentHealth> | null>(null);
  const checkOptions = buildCheckOptions(agentServices);
  const activeChecks: AnalysisCheckOptions = {
    ...checks,
    codeQuality: checks.codeQuality && tools.some((tool) => tool === "ruff" || tool === "pylint"),
    complexity: checks.complexity && tools.includes("radon"),
  };
  const selectedTools = tools.filter((tool) => tool === "radon" ? activeChecks.complexity : activeChecks.codeQuality);
  const anyCheckSelected = Object.values(activeChecks).some(Boolean);
  let validPastedPath = "";
  try {
    validPastedPath = validatePythonPath(pastedFilename);
  } catch {
    validPastedPath = "";
  }

  useEffect(() => {
    if (initialFiles.length) { setFiles(initialFiles); setInputMode("files"); }
    if (initialProjectName) setProjectName(initialProjectName);
  }, [initialFiles, initialProjectName]);

  useEffect(() => {
    let active = true;
    void apiClient.get<{ services?: Record<string, AgentHealth> }>("/api/system/agents")
      .then((payload) => { if (active) setAgentServices(payload.services ?? {}); })
      .catch(() => { if (active) setAgentServices({}); });
    return () => { active = false; };
  }, []);

  async function start() {
    if (runInProgress) {
      setSubmitError("A validation run is already in progress. Wait for it to finish before starting another.");
      return;
    }
    if (submitting) return;
    setSubmitting(true);
    setSubmitError("");
    try {
      await onStart(inputMode === "code" ? [{ path: validPastedPath, content: code }] : files, selectedTools, projectName.trim(), existingProjectId, activeChecks);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Validation could not be started.");
    } finally {
      setSubmitting(false);
    }
  }

  function setCheck<K extends keyof AnalysisCheckOptions>(key: K, value: AnalysisCheckOptions[K]) {
    setPreset("custom");
    setChecks((current) => ({ ...current, [key]: value }));
    if (key === "complexity" && value) setTools((current) => current.includes("radon") ? current : [...current, "radon"]);
    if (key === "codeQuality" && value) setTools((current) => current.some((tool) => tool === "ruff" || tool === "pylint") ? current : [...current, "ruff"]);
  }

  function setTool(tool: QualityTool, selected: boolean) {
    setPreset("custom");
    const nextTools = selected ? [...new Set([...tools, tool])] : tools.filter((item) => item !== tool);
    setTools(nextTools);
    if (tool === "radon") setChecks((current) => ({ ...current, complexity: selected }));
    if (tool === "ruff" || tool === "pylint") setChecks((current) => ({ ...current, codeQuality: nextTools.some((item) => item === "ruff" || item === "pylint") }));
  }

  function useRecommendedPreset() {
    setChecks(DEFAULT_ANALYSIS_CHECKS);
    setTools(TOOL_OPTIONS);
    setPreset("recommended");
  }

  return (
    <section className="page page--upload">
      <div className="page-heading">
        <div>
          <div className="kicker">New analysis <span>01 / 04</span></div>
          <h1>Choose checks.<br /><em>Start analysis.</em></h1>
          <p>Select the checks and available quality tools for this Python project.</p>
        </div>
        <div className="heading-stamp"><span>PY</span><strong>Python<br />analysis</strong></div>
      </div>

      <div className="project-input-meta"><label className="project-name-field">Project name<input value={projectName} maxLength={120} readOnly={Boolean(existingProjectId)} onChange={(event) => setProjectName(event.target.value)} /></label></div>
      {projectLoadError && <p className="inline-error" role="alert">{projectLoadError}</p>}
      <UploadInputMethod inputMode={inputMode} onInputModeChange={setInputMode} onFilesReady={setFiles} code={code} onCodeChange={setCode} filename={pastedFilename} onFilenameChange={setPastedFilename} validPath={validPastedPath} />

      <section className="analysis-checks" aria-labelledby="analysis-checks-title">
        <div className="analysis-config-heading"><div><p className="kicker">MAIN CONFIGURATION</p><h2 id="analysis-checks-title">Analysis Checks</h2><p>What would you like to validate?</p></div><AnalysisPresetControl preset={preset} onRecommended={useRecommendedPreset} onCustom={() => setPreset("custom")} /></div>
        <AnalysisCheckCards options={checkOptions} checks={checks} onChange={setCheck} />
        <AnalysisCheckWarnings checks={checks} activeChecks={activeChecks} />
      </section>

      <section className="code-quality-tools" aria-labelledby="quality-tools-title">
        <div className="analysis-config-heading"><div><p className="kicker">QUALITY EVIDENCE</p><h2 id="quality-tools-title">Code Quality Tools</h2><p>Choose which tools support the selected checks. Complexity analysis requires Radon.</p></div></div>
        <QualityToolCards tools={tools} selectedTools={selectedTools} onChange={setTool} />
      </section>

      <details className="advanced-settings">
        <summary>Advanced Settings</summary>
        <p className="analysis-capability-note">Per-analysis sandbox timeout, memory, CPU, and network settings are not supported by the connected backend.</p>
      </details>

      <AnalysisSummary checks={activeChecks} tools={selectedTools} />
      <StartAnalysisControls disabled={submitting || runInProgress || (inputMode === "files" && files.length === 0) || (inputMode === "code" && (!code.trim() || !validPastedPath)) || !anyCheckSelected || (checks.codeQuality && !activeChecks.codeQuality) || (checks.complexity && !activeChecks.complexity) || !projectName.trim() || Boolean(projectLoadError)} submitting={submitting} runInProgress={runInProgress} error={submitError} onStart={() => void start()} />
      <RecentRuns history={history} onOpenHistory={onOpenHistory} />
    </section>
  );
}
