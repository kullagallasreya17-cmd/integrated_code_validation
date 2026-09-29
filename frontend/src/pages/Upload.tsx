import { FileUpload } from "../components/FileUpload";
import { useEffect, useState } from "react";
import { CodeEditor } from "../components/CodeEditor";
import type { ProjectFile, QualityTool, RunHistoryEntry } from "../types/finding";
import { ConfigurationPanel } from "../components/ConfigurationPanel";
import { DEFAULT_ANALYSIS_CONFIGURATION, validateAnalysisConfiguration, type AnalysisConfiguration } from "../api/configuration";
import { validatePythonPath } from "../api/files";

interface UploadPageProps {
  onStart: (files: ProjectFile[], tools: QualityTool[], securityTools?: never[], projectName?: string, configuration?: AnalysisConfiguration, existingProjectId?: string) => Promise<void>;
  history: RunHistoryEntry[];
  onOpenHistory: (entry: RunHistoryEntry) => void;
  initialFiles?: ProjectFile[];
  initialProjectName?: string;
  existingProjectId?: string;
  projectLoadError?: string;
  runInProgress?: boolean;
}

const TOOL_OPTIONS: QualityTool[] = ["ruff", "pylint", "radon"];
const TOOL_ICON: Record<QualityTool, string> = { ruff: "R", pylint: "P", radon: "C" };
const TOOL_DESCRIPTION: Record<QualityTool, string> = {
  ruff: "Fast linting · Requested for this run",
  pylint: "Code quality · Requested for this run",
  radon: "Complexity · Requested for this run",
};

export function UploadPage({ onStart, history, onOpenHistory, initialFiles = [], initialProjectName, existingProjectId, projectLoadError, runInProgress = false }: Readonly<UploadPageProps>) {
  const [files, setFiles] = useState<ProjectFile[]>(initialFiles);
  const [projectName, setProjectName] = useState(initialProjectName ?? "Python project");
  const [analysisConfiguration, setAnalysisConfiguration] = useState(DEFAULT_ANALYSIS_CONFIGURATION);
  const [tools, setTools] = useState<QualityTool[]>(TOOL_OPTIONS);
  const [language, setLanguage] = useState("python");
  const [inputMode, setInputMode] = useState<"files" | "code">("files");
  const [code, setCode] = useState("def example(value):\n    return value\n");
  const [pastedFilename, setPastedFilename] = useState("pasted-code.py");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
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
      await onStart(inputMode === "code" ? [{ path: validPastedPath, content: code }] : files, tools, [], projectName.trim(), analysisConfiguration, existingProjectId);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Validation could not be started.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="page page--upload">
      <div className="page-heading">
        <div>
          <div className="kicker">Analysis workspace <span>01 / 04</span></div>
          <h1>Analyze.<br /><em>Repair. Validate.</em></h1>
          <p>AI-powered code analysis with multi-agent validation and automated repair evidence for every change.</p>
        </div>
        <div className="heading-stamp"><span>PY</span><strong>Python<br />analysis</strong></div>
      </div>

      <fieldset className="input-tabs" aria-label="Code input method">
        <button type="button" aria-pressed={inputMode === "files"} className={inputMode === "files" ? "input-tab input-tab--active" : "input-tab"} onClick={() => setInputMode("files")}>Project files <small>UPLOAD</small></button>
        <button type="button" aria-pressed={inputMode === "code"} className={inputMode === "code" ? "input-tab input-tab--active" : "input-tab"} onClick={() => setInputMode("code")}>Quick code <small>PASTE</small></button>
      </fieldset>
      <p className="python-only-notice">Python projects only. Non-Python source files are rejected before analysis.</p>
      <label className="project-name-field">Project name<input value={projectName} maxLength={120} readOnly={Boolean(existingProjectId)} onChange={(event) => setProjectName(event.target.value)} /></label>
      {projectLoadError && <p className="inline-error" role="alert">{projectLoadError}</p>}
      <div className="language-row"><label htmlFor="language">Language</label><select id="language" value={language} onChange={(event) => setLanguage(event.target.value)}><option value="python">Python</option></select><span>Initial language support</span></div>
      {inputMode === "files" ? <FileUpload onFilesReady={setFiles} /> : (
        <div className="code-entry">
          <div className="code-entry__bar"><span className="window-dots"><i /><i /><i /></span><label className="code-entry__filename">Filename<input aria-label="Filename for pasted Python code" value={pastedFilename} maxLength={180} onChange={(event) => setPastedFilename(event.target.value)} /></label><span className="code-entry__meta">Python 3.11</span></div>
          <CodeEditor path={validPastedPath || "pasted-code.py"} value={code} onChange={setCode} height="250px" />
          {!validPastedPath && <p className="inline-error" role="alert">Enter a relative Python filename ending in .py. Paths cannot be absolute or contain '..'.</p>}
        </div>
      )}

      <fieldset className="tool-settings">
        <legend>Quality checks <span>Choose the evidence sources for this run</span></legend>
        {TOOL_OPTIONS.map((tool) => (
          <label key={tool} className={tools.includes(tool) ? "tool-card tool-card--selected" : "tool-card"}>
            <input
              type="checkbox"
              checked={tools.includes(tool)}
              onChange={() =>
                setTools((selected) =>
                  selected.includes(tool) ? selected.filter((item) => item !== tool) : [...selected, tool]
                )
              }
            />
            <span className="tool-card__icon">{TOOL_ICON[tool]}</span>
            <span><strong>{tool}</strong><small>{TOOL_DESCRIPTION[tool]}</small></span>
            <b>{tools.includes(tool) ? "✓" : ""}</b>
          </label>
        ))}
      </fieldset>

      <ConfigurationPanel mode="analysis" onChange={setAnalysisConfiguration} />

      <button
        className="btn btn--primary"
        disabled={submitting || runInProgress || (inputMode === "files" && files.length === 0) || (inputMode === "code" && (!code.trim() || !validPastedPath)) || tools.length === 0 || language !== "python" || !projectName.trim() || !validateAnalysisConfiguration(analysisConfiguration) || Boolean(projectLoadError)}
        onClick={() => void start()}
      >
        {submitting ? "Validation running..." : "Start validation"} {!submitting && <span>→</span>}
      </button>
      {(submitting || runInProgress) && <p className="analysis-pulse" role="status" aria-live="polite">Sending code to the orchestrator and waiting for validation results...</p>}
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
