import { FileUpload } from "../components/FileUpload";
import { useState } from "react";
import { CodeEditor } from "../components/CodeEditor";
import type { ProjectFile, QualityTool, RunHistoryEntry } from "../types/finding";

interface UploadPageProps {
  onStart: (files: ProjectFile[], tools: QualityTool[], securityTools?: never[]) => void;
  history: RunHistoryEntry[];
  onOpenHistory: (entry: RunHistoryEntry) => void;
}

const TOOL_OPTIONS: QualityTool[] = ["ruff", "pylint", "radon"];

export function UploadPage({ onStart, history, onOpenHistory }: UploadPageProps) {
  const [files, setFiles] = useState<ProjectFile[]>([]);
  const [tools, setTools] = useState<QualityTool[]>(TOOL_OPTIONS);
  const [language, setLanguage] = useState("python");
  const [inputMode, setInputMode] = useState<"files" | "code">("files");
  const [code, setCode] = useState("def example(value):\n    return value\n");

  function start() {
    onStart(inputMode === "code" ? [{ path: "main.py", content: code }] : files, tools, []);
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

      <div className="input-tabs" role="tablist" aria-label="Code input method">
        <button className={inputMode === "files" ? "input-tab input-tab--active" : "input-tab"} onClick={() => setInputMode("files")}>Project files <small>UPLOAD</small></button>
        <button className={inputMode === "code" ? "input-tab input-tab--active" : "input-tab"} onClick={() => setInputMode("code")}>Quick code <small>PASTE</small></button>
      </div>
      <div className="language-row"><label htmlFor="language">Language</label><select id="language" value={language} onChange={(event) => setLanguage(event.target.value)}><option value="python">Python</option></select><span>Initial language support</span></div>
      {inputMode === "files" ? <FileUpload onFilesReady={setFiles} /> : (
        <div className="code-entry">
          <div className="code-entry__bar"><span className="window-dots"><i /><i /><i /></span><span>main.py</span><span className="code-entry__meta">Python 3.11</span></div>
          <CodeEditor path="input-main.py" value={code} onChange={setCode} height="250px" />
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
            <span className="tool-card__icon">{tool === "ruff" ? "R" : tool === "pylint" ? "P" : "C"}</span>
            <span><strong>{tool}</strong><small>{tool === "radon" ? "Complexity · Ready" : tool === "ruff" ? "Fast linting · Ready" : "Code quality · Ready"}</small></span>
            <b>{tools.includes(tool) ? "✓" : ""}</b>
          </label>
        ))}
      </fieldset>

      <button
        className="btn btn--primary"
        disabled={(inputMode === "files" && files.length === 0) || (inputMode === "code" && !code.trim()) || tools.length === 0 || language !== "python"}
        onClick={start}
      >
        Start validation <span>→</span>
      </button>

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
