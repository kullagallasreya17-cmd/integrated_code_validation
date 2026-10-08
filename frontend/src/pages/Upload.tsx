import { FileUpload } from "../components/FileUpload";
import { useEffect, useState } from "react";
import { CodeEditor } from "../components/CodeEditor";
import type { ProjectFile, QualityTool, RunHistoryEntry } from "../types/finding";
import { DEFAULT_ANALYSIS_CHECKS, type AnalysisCheckOptions } from "../api/configuration";
import { validatePythonPath } from "../api/files";

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

const CHECK_OPTIONS: Array<{ key: keyof AnalysisCheckOptions; title: string; description: string; available: boolean }> = [
  { key: "codeQuality", title: "Code Quality", description: "Run Ruff and Pylint against Python files.", available: true },
  { key: "security", title: "Security", description: "Not available in this deployment.", available: false },
  { key: "bugResource", title: "Bug & Resource Analysis", description: "Not available in this deployment.", available: false },
  { key: "complexity", title: "Complexity Analysis", description: "Run Radon to identify complexity hotspots.", available: true },
  { key: "automatedRepair", title: "Automated Repair", description: "Not available in this deployment.", available: false },
  { key: "finalValidation", title: "Final Validation", description: "Not available in this deployment.", available: false },
];

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

      <fieldset className="input-tabs" aria-label="Code input method">
        <button type="button" aria-pressed={inputMode === "files"} className={inputMode === "files" ? "input-tab input-tab--active" : "input-tab"} onClick={() => setInputMode("files")}>Project files <small>UPLOAD</small></button>
        <button type="button" aria-pressed={inputMode === "code"} className={inputMode === "code" ? "input-tab input-tab--active" : "input-tab"} onClick={() => setInputMode("code")}>Quick code <small>PASTE</small></button>
      </fieldset>
      <div className="project-input-meta"><label className="project-name-field">Project name<input value={projectName} maxLength={120} readOnly={Boolean(existingProjectId)} onChange={(event) => setProjectName(event.target.value)} /></label></div>
      {projectLoadError && <p className="inline-error" role="alert">{projectLoadError}</p>}
      {inputMode === "files" ? <FileUpload onFilesReady={setFiles} /> : (
        <div className="code-entry">
          <div className="code-entry__bar"><span className="window-dots"><i /><i /><i /></span><label className="code-entry__filename">Filename<input aria-label="Filename for pasted Python code" value={pastedFilename} maxLength={180} onChange={(event) => setPastedFilename(event.target.value)} /></label><span className="code-entry__meta">Python 3.11</span></div>
          <CodeEditor path={validPastedPath || "pasted-code.py"} value={code} onChange={setCode} height="250px" />
          {!validPastedPath && <p className="inline-error" role="alert">Enter a relative Python filename ending in .py. Paths cannot be absolute or contain '..'.</p>}
        </div>
      )}

      <section className="analysis-checks" aria-labelledby="analysis-checks-title">
        <div className="analysis-config-heading"><div><p className="kicker">MAIN CONFIGURATION</p><h2 id="analysis-checks-title">Analysis Checks</h2><p>What would you like to validate?</p></div><div className="analysis-presets" role="group" aria-label="Analysis preset"><button type="button" className={preset === "recommended" ? "analysis-preset analysis-preset--active" : "analysis-preset"} onClick={useRecommendedPreset}>Recommended</button><button type="button" className={preset === "custom" ? "analysis-preset analysis-preset--active" : "analysis-preset"} onClick={() => setPreset("custom")}>Custom</button></div></div>
        <div className="analysis-check-grid">{CHECK_OPTIONS.map(({ key, title, description, available }) => <label className={`analysis-check-card${checks[key] ? " analysis-check-card--selected" : ""}${available ? "" : " analysis-check-card--unavailable"}`} key={key}><input type="checkbox" checked={checks[key]} disabled={!available} onChange={(event) => setCheck(key, event.target.checked)} /><span className="analysis-check-card__mark" aria-hidden="true">{checks[key] ? "✓" : !available ? "–" : ""}</span><span><strong>{title}</strong><small>{description}</small>{!available && <b>Unavailable</b>}</span></label>)}</div>
        {checks.codeQuality && !activeChecks.codeQuality && <p className="inline-error" role="status">Select Ruff or Pylint to run Code Quality analysis.</p>}
        {checks.complexity && !activeChecks.complexity && <p className="inline-error" role="status">Select Radon to run Complexity Analysis.</p>}
      </section>

      <section className="code-quality-tools" aria-labelledby="quality-tools-title">
        <div className="analysis-config-heading"><div><p className="kicker">QUALITY EVIDENCE</p><h2 id="quality-tools-title">Code Quality Tools</h2><p>Choose which tools support the selected checks. Complexity analysis requires Radon.</p></div></div>
        <div className="quality-tool-grid">{TOOL_OPTIONS.map((tool) => { const configured = selectedTools.includes(tool); return <label key={tool} className={tools.includes(tool) ? "quality-tool-card quality-tool-card--selected" : "quality-tool-card"}><input type="checkbox" checked={tools.includes(tool)} onChange={(event) => setTool(tool, event.target.checked)} /><span className="quality-tool-card__mark" aria-hidden="true">{tools.includes(tool) ? "✓" : ""}</span><span><strong>{tool[0].toUpperCase() + tool.slice(1)}</strong><small>{TOOL_DESCRIPTION[tool]}</small></span><b>{configured ? "Configured" : tools.includes(tool) ? "Disabled by check" : "Not selected"}</b></label>; })}</div>
      </section>

      <details className="advanced-settings">
        <summary>Advanced Settings</summary>
        <p className="analysis-capability-note">Per-analysis sandbox timeout, memory, CPU, and network settings are not supported by the connected backend.</p>
      </details>

      <section className="validation-summary" aria-label="Analysis summary">
        <div><p className="kicker">READY TO RUN</p><h2>Analysis Summary</h2></div>
        <div><span>Checks</span><p>{[
          activeChecks.codeQuality ? "Code Quality" : undefined,
          activeChecks.security ? "Security" : undefined,
          activeChecks.bugResource ? "Bugs & Resources" : undefined,
          activeChecks.complexity ? "Complexity" : undefined,
          activeChecks.automatedRepair ? "Repair" : undefined,
          activeChecks.finalValidation ? "Validation" : undefined,
        ].filter(Boolean).join(" · ") || "No checks selected"}</p></div>
        <div><span>Tools</span><p>{selectedTools.map((tool) => tool[0].toUpperCase() + tool.slice(1)).join(" · ") || "None selected"}</p></div>
        <div><span>Execution</span><p>Backend-managed; per-analysis sandbox limits unavailable</p></div>
      </section>

      <button
        className="btn btn--primary"
        disabled={submitting || runInProgress || (inputMode === "files" && files.length === 0) || (inputMode === "code" && (!code.trim() || !validPastedPath)) || !anyCheckSelected || (checks.codeQuality && !activeChecks.codeQuality) || (checks.complexity && !activeChecks.complexity) || !projectName.trim() || Boolean(projectLoadError)}
        onClick={() => void start()}
      >
        {submitting ? "Analysis running..." : "Start Analysis"} {!submitting && <span>→</span>}
      </button>
      {(submitting || runInProgress) && <p className="analysis-pulse" role="status" aria-live="polite">Running the selected analysis checks...</p>}
      {submitError && <p className="inline-error" role="alert">{submitError}</p>}

      {history.length > 0 && (
        <section className="past-runs">
          <div className="section-label"><h2>Recent runs</h2><span>{history.length} saved locally</span></div>
          <ul className="history-list">
            {history.map((entry) => (
              <li key={`${entry.project_id}-${entry.timestamp}`}>
                <button className="btn btn--link" onClick={() => onOpenHistory(entry)}>
                  <span className="history-list__icon">↗</span><span><strong>{entry.project_id}</strong><small>{new Date(entry.timestamp).toLocaleString()}</small></span><b className={`status-pill status-pill--${entry.validation_status}`}>{entry.validation_status}</b>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}
