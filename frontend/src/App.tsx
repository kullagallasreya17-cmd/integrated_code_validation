import { useEffect, useState } from "react";
import { UploadPage } from "./pages/Upload";
import { AnalysisPage } from "./pages/Analysis";
import { ResultsPage } from "./pages/Results";
import { api } from "./services/api";
import type {
  ProgressEvent,
  ProjectFile,
  QualityTool,
  SecurityTool,
  RunHistoryEntry,
  WorkflowRunResponse,
} from "./types/finding";
import { AgentStatusPanel } from "./components/AgentStatusPanel";
import { ToolStatusPanel } from "./components/ToolStatusPanel";
import { FindingsReviewPage } from "./pages/FindingsReview";
import { RepairHistoryPage } from "./pages/RepairHistory";
import { AuthPage, type AuthFormValues } from "./pages/AuthPage";
import { DashboardPage } from "./pages/Dashboard";
import { AgentCenter } from "./pages/AgentCenter";
import "./App.css";

type Stage = "auth" | "dashboard" | "upload" | "analysis" | "results" | "findings" | "history" | "agents" | "error";
type AuthMode = "signin" | "signup";

export default function App() {
  const [stage, setStage] = useState<Stage>("auth");
  const [authMode, setAuthMode] = useState<AuthMode>("signin");
  const [originalFiles, setOriginalFiles] = useState<ProjectFile[]>([]);
  const [result, setResult] = useState<WorkflowRunResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [activeStepIndex, setActiveStepIndex] = useState(0);
  const [progressMessage, setProgressMessage] = useState<string | undefined>();
  const [history, setHistory] = useState<RunHistoryEntry[]>(() => {
    try {
      return JSON.parse(localStorage.getItem("coding-validation-run-history") ?? "[]") as RunHistoryEntry[];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    localStorage.setItem("coding-validation-run-history", JSON.stringify(history));
  }, [history]);

  function handleAuthSubmit(values: AuthFormValues) {
    console.info("Auth submitted", values);
    setStage("dashboard");
  }

  async function handleStart(files: ProjectFile[], tools: QualityTool[], securityTools: SecurityTool[] = []) {
    setOriginalFiles(files);
    setStage("analysis");
    setErrorMessage(null);
    setActiveStepIndex(0);
    setProgressMessage("Starting analysis");

    try {
      const projectId = `proj-${Date.now()}`;
      const response = await api.startAnalysis(
        { project_id: projectId, files, tools, project_context: { security_tools: securityTools } },
        (progress: ProgressEvent) => {
          const stepIndexes: Record<string, number> = {
            understand: 0,
            analyze: 1,
            aggregate: 3,
            explain_prioritize: 4,
            repair: 5,
            validate: 6,
            reanalyze: 7,
            compare: 8,
            finalize: 9,
          };
          setActiveStepIndex(stepIndexes[progress.step] ?? 0);
          setProgressMessage(progress.message);
        },
      );
      setResult(response);
      setHistory((entries) => [
        {
          project_id: response.project_id,
          timestamp: new Date().toISOString(),
          validation_status: response.validation_status,
          result: response,
          originalFiles: files,
        },
        ...entries.filter((entry) => entry.project_id !== response.project_id),
      ]);
      setStage("results");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Backend unreachable");
      setStage("error");
    }
  }

  function openHistory(entry: RunHistoryEntry) {
    setOriginalFiles(entry.originalFiles);
    setResult(entry.result);
    setStage("results");
    setErrorMessage(null);
  }

  function rerun() {
    if (originalFiles.length > 0) handleStart(originalFiles, ["ruff", "pylint", "radon"]);
  }

  function reset() {
    setStage("auth");
    setOriginalFiles([]);
    setResult(null);
    setErrorMessage(null);
    setProgressMessage(undefined);
  }

  const currentFindings = result?.findings ?? history.flatMap((entry) => entry.result.findings);

  function setWorkspaceStage(nextStage: Stage) {
    setErrorMessage(null);
    if (nextStage === "upload") setStage("upload");
    else if (nextStage === "auth") reset();
    else setStage(nextStage);
  }

  return (
    <main className="app-shell">
      {stage === "auth" ? (
        <AuthPage mode={authMode} onModeChange={setAuthMode} onSubmit={handleAuthSubmit} />
      ) : (
        <>
          <header className="topbar">
            <button className="brand" onClick={() => setStage("dashboard")} aria-label="Return to dashboard">
              <span className="brand-mark">CV</span>
              <span>
                <strong>Code validation</strong>
                <small>autonomous repair workspace</small>
              </span>
            </button>

            <div className="topbar__actions">
              <div className="topbar__status"><span className="status-dot" /> Analysis engine online</div>
              <button className="btn btn--ghost" onClick={reset}>Log out</button>
            </div>
          </header>

          <div className="workspace">
            <aside className="sidebar">
              <div className="sidebar__eyebrow">Workspace</div>
              <button className={`sidebar__item ${stage === "dashboard" ? "sidebar__item--active" : ""}`} onClick={() => setWorkspaceStage("dashboard")}><span>00</span> Overview</button>
              <button className={`sidebar__item ${stage === "upload" ? "sidebar__item--active" : ""}`} onClick={() => setWorkspaceStage("upload")}><span>01</span> New analysis</button>
              <button className={`sidebar__item ${stage === "findings" ? "sidebar__item--active" : ""}`} onClick={() => setWorkspaceStage("findings")}><span>02</span> Findings review</button>
              <button className={`sidebar__item ${stage === "history" ? "sidebar__item--active" : ""}`} onClick={() => setWorkspaceStage("history")}><span>03</span> Repair history</button>
              <button className={`sidebar__item ${stage === "agents" ? "sidebar__item--active" : ""}`} onClick={() => setWorkspaceStage("agents")}><span>04</span> Agent control room</button>
              <div className="sidebar__rule" />
              <div className="sidebar__eyebrow">Pipeline</div>
              <div className="pipeline-mini"><i /><span><strong>Understand</strong><small>Project structure &amp; code analysis</small></span></div>
              <div className="pipeline-mini"><i /><span><strong>Detect issues</strong><small>Structure · quality · risk</small></span></div>
              <div className="pipeline-mini"><i /><span><strong>Repair &amp; validate</strong><small>Candidate → sandbox → evidence</small></span></div>
              <div className="pipeline-mini"><i /><span><strong>Report</strong><small>Findings · fixes · evidence</small></span></div>
            </aside>

            <main className="content">
              {stage === "dashboard" && <DashboardPage history={history} latestResult={result} onStart={() => setWorkspaceStage("upload")} onOpenResults={() => result && setWorkspaceStage("results")} onOpenHistory={() => setWorkspaceStage("history")} />}
              {stage === "upload" && (
                <>
                  <UploadPage onStart={handleStart} history={history} onOpenHistory={openHistory} />
                  <AgentStatusPanel activeStep={0} progressMessage="Ready to coordinate analysis" preview />
                  <ToolStatusPanel quality={["Ruff", "Pylint", "Radon"]} />
                </>
              )}

              {stage === "analysis" && (
                <>
                  <AnalysisPage activeStepIndex={activeStepIndex} progressMessage={progressMessage} />
                  <AgentStatusPanel activeStep={activeStepIndex} progressMessage={progressMessage} />
                </>
              )}

              {stage === "results" && result && (
                <ResultsPage originalFiles={originalFiles} result={result} onRerun={rerun} />
              )}

              {stage === "findings" && <FindingsReviewPage findings={currentFindings} onNewAnalysis={() => setWorkspaceStage("upload")} />}
              {stage === "history" && <RepairHistoryPage history={history} onOpen={openHistory} onNewAnalysis={() => setWorkspaceStage("upload")} />}
              {stage === "agents" && <AgentCenter />}

              {stage === "error" && (
                <section className="page page--error">
                  <h1>Something went wrong</h1>
                  <p>{errorMessage}</p>
                  <button className="btn" onClick={() => setStage("upload")}>
                    Try again
                  </button>
                </section>
              )}
            </main>
          </div>
        </>
      )}
    </main>
  );
}
