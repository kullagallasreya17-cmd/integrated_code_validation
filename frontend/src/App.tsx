import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Link, NavLink, Outlet, Route, Routes, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { AgentStatusPanel } from "./components/AgentStatusPanel";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { RequireAuth } from "./components/RequireAuth";
import { ToolStatusPanel } from "./components/ToolStatusPanel";
import type { ProgressEvent, ProjectFile, QualityTool, RunHistoryEntry, SecurityTool, WorkflowRunResponse } from "./types/finding";
import { api } from "./services/api";
import { AgentCenter } from "./pages/AgentCenter";
import { AnalysisPage } from "./pages/Analysis";
import { DashboardPage } from "./pages/Dashboard";
import { FindingsReviewPage } from "./pages/FindingsReview";
import { LoginRoute } from "./pages/LoginRoute";
import { RepairHistoryPage } from "./pages/RepairHistory";
import { ResultsPage } from "./pages/Results";
import { UploadPage } from "./pages/Upload";
import { ProjectDetailPage, ProjectsPage } from "./pages/Projects";
import { usePermission } from "./auth/permissions";
import { AdminUsersPage } from "./pages/Admin";
import { AnalysisTabs } from "./analysis/AnalysisTabs";
import { createProject, getProject } from "./api/projects";
import { getProjectFiles } from "./api/files";
import type { ProjectDetail, ProjectFile as ApiProjectFile } from "./api/types";
import { DEFAULT_ANALYSIS_CONFIGURATION, type AnalysisConfiguration } from "./api/configuration";
import { AdminSettingsPage } from "./pages/AdminSettings";
import { useAuth } from "./context/AuthContext";
import { mocksEnabled } from "./api/client";
import "./App.css";

type StartHandler = (files: ProjectFile[], tools: QualityTool[], securityTools?: SecurityTool[], projectName?: string, configuration?: AnalysisConfiguration, existingProjectId?: string) => Promise<void>;

interface WorkspaceState {
  readonly history: RunHistoryEntry[];
  readonly result: WorkflowRunResponse | null;
  readonly originalFiles: ProjectFile[];
  readonly activeStepIndex: number;
  readonly progressMessage?: string;
  readonly errorMessage: string | null;
  readonly handleStart: StartHandler;
  readonly openHistory: (entry: RunHistoryEntry) => void;
  readonly rerun: () => void;
}

const WorkspaceContext = createContext<WorkspaceState | null>(null);
const EMPTY_WORKSPACE: WorkspaceState = {
  history: [], result: null, originalFiles: [], activeStepIndex: 0, errorMessage: null,
  handleStart: async () => undefined, openHistory: () => undefined, rerun: () => undefined,
};

function useWorkspace(): WorkspaceState {
  return useContext(WorkspaceContext) ?? EMPTY_WORKSPACE;
}

export default function App() {
  const navigate = useNavigate();
  const [originalFiles, setOriginalFiles] = useState<ProjectFile[]>([]);
  const [result, setResult] = useState<WorkflowRunResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [activeStepIndex, setActiveStepIndex] = useState(0);
  const [progressMessage, setProgressMessage] = useState<string>();
  const [history, setHistory] = useState<RunHistoryEntry[]>(() => {
    try {
      return JSON.parse(sessionStorage.getItem("coding-validation-run-history") ?? "[]") as RunHistoryEntry[];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    sessionStorage.setItem("coding-validation-run-history", JSON.stringify(history));
  }, [history]);

  useEffect(() => {
    const clearWorkspace = () => {
      sessionStorage.removeItem("coding-validation-run-history");
      localStorage.removeItem("coding-validation-run-history");
      setHistory([]);
      setOriginalFiles([]);
      setResult(null);
      setErrorMessage(null);
      setActiveStepIndex(0);
      setProgressMessage(undefined);
    };
    const expireSession = (event: Event) => {
      const detail = (event as CustomEvent<{ from?: string }>).detail;
      navigate("/login", { replace: true, state: { from: detail?.from ?? `${window.location.pathname}${window.location.search}${window.location.hash}`, expired: true } });
    };
    window.addEventListener("coding-validation:clear-user-data", clearWorkspace);
    window.addEventListener("coding-validation:session-expired", expireSession);
    return () => {
      window.removeEventListener("coding-validation:clear-user-data", clearWorkspace);
      window.removeEventListener("coding-validation:session-expired", expireSession);
    };
  }, [navigate]);

  const handleStart = useCallback(async (files: ProjectFile[], tools: QualityTool[], securityTools: SecurityTool[] = [], projectName = "Python project", configuration = DEFAULT_ANALYSIS_CONFIGURATION, existingProjectId?: string): Promise<void> => {
    setOriginalFiles(files);
    setResult(null);
    setErrorMessage(null);
    setActiveStepIndex(0);
    setProgressMessage("Starting analysis");
    try {
      const projectId = existingProjectId ?? (await createProject({ name: projectName, files, project_context: { ...configuration } })).project_id;
      navigate(`/analysis/${encodeURIComponent(projectId)}`);
      const response = await api.startAnalysis(
        { project_id: projectId, files, tools, project_context: { ...configuration, security_tools: securityTools } },
        (progress: ProgressEvent) => {
          const stepIndexes: Record<string, number> = {
            understand: 0, analyze: 1, aggregate: 3, explain_prioritize: 4,
            repair: 5, validate: 6, reanalyze: 7, compare: 8, finalize: 9,
          };
          setActiveStepIndex(stepIndexes[progress.step] ?? 0);
          setProgressMessage(progress.message);
        },
      );
      const completedRun = { ...response, analysis_configuration: configuration };
      setResult(completedRun);
      setHistory((entries) => [
        { project_id: response.project_id, timestamp: new Date().toISOString(), validation_status: response.validation_status, result: completedRun, originalFiles: files },
        ...entries.filter((entry) => entry.project_id !== response.project_id),
      ]);
      navigate(`/analysis/${encodeURIComponent(response.project_id)}/results`);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "The analysis could not be completed.");
    }
  }, [navigate]);

  const openHistory = useCallback((entry: RunHistoryEntry): void => {
    setOriginalFiles(entry.originalFiles);
    setResult(entry.result);
    setErrorMessage(null);
    navigate(`/analysis/${encodeURIComponent(entry.project_id)}/results`);
  }, [navigate]);

  const rerun = useCallback((): void => {
    if (originalFiles.length > 0) void handleStart(originalFiles, ["ruff", "pylint", "radon"]);
  }, [handleStart, originalFiles]);

  const value = useMemo<WorkspaceState>(
    () => ({ history, result, originalFiles, activeStepIndex, progressMessage, errorMessage, handleStart, openHistory, rerun }),
    [history, result, originalFiles, activeStepIndex, progressMessage, errorMessage, handleStart, openHistory, rerun],
  );

  return (
    <ErrorBoundary>
      <WorkspaceContext.Provider value={value}>
        <Routes>
          <Route path="/login" element={<LoginRoute />} />
          <Route element={<RequireAuth><WorkspaceLayout /></RequireAuth>}>
            <Route index element={<DashboardRoute />} />
            <Route path="projects" element={<ProjectsPage />} />
            <Route path="projects/:id" element={<ProjectDetailPage />} />
            <Route path="projects/new" element={<RequireAuth capability="upload"><UploadRoute /></RequireAuth>} />
            <Route path="analysis/:id" element={<AnalysisRoute />} />
            <Route path="analysis/:id/findings" element={<FindingsRoute />} />
            <Route path="analysis/:id/results" element={<ResultsRoute />} />
            <Route path="reports/:id" element={<ResultsRoute />} />
            <Route path="analysis/:id/repair" element={<UnavailablePage title="Repair workspace" />} />
            <Route path="analysis/:id/validation" element={<UnavailablePage title="Validation details" />} />
            <Route path="history" element={<HistoryRoute />} />
            <Route path="agents" element={<AgentCenter />} />
            <Route path="admin" element={<RequireAuth capability="adminAccess"><AdminUsersPage /></RequireAuth>} />
            <Route path="admin/settings" element={<RequireAuth capability="adminAccess"><AdminSettingsPage /></RequireAuth>} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </WorkspaceContext.Provider>
    </ErrorBoundary>
  );
}

function WorkspaceLayout() {
  const { user, logout } = useAuth();
  const canManageUsers = usePermission("adminAccess");
  const canStartAnalysis = usePermission("createAnalysis");

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link className="brand" to="/" aria-label="Return to dashboard">
          <span className="brand-mark">CV</span>
          <span><strong>Code validation</strong><small>autonomous repair workspace</small></span>
        </Link>
        <div className="topbar__actions">
          {mocksEnabled() && <span className="mock-mode-badge">MOCK MODE</span>}
          <span className="topbar__status"><span className="status-dot" />{user?.email}</span>
          <button className="btn btn--ghost" onClick={logout}>Log out</button>
        </div>
      </header>
      <div className="workspace">
        <aside className="sidebar" aria-label="Workspace navigation">
          <div className="sidebar__eyebrow">Workspace</div>
          <NavLink className={({ isActive }) => `sidebar__item${isActive ? " sidebar__item--active" : ""}`} to="/" end><span>00</span> Overview</NavLink>
          <NavLink className={({ isActive }) => `sidebar__item${isActive ? " sidebar__item--active" : ""}`} to="/projects"><span>00</span> Projects</NavLink>
          {canStartAnalysis && <NavLink className={({ isActive }) => `sidebar__item${isActive ? " sidebar__item--active" : ""}`} to="/projects/new"><span>01</span> New analysis</NavLink>}
          <NavLink className={({ isActive }) => `sidebar__item${isActive ? " sidebar__item--active" : ""}`} to="/history"><span>02</span> History</NavLink>
          <NavLink className={({ isActive }) => `sidebar__item${isActive ? " sidebar__item--active" : ""}`} to="/agents"><span>03</span> Agent control room</NavLink>
          {canManageUsers && <NavLink className={({ isActive }) => `sidebar__item${isActive ? " sidebar__item--active" : ""}`} to="/admin"><span>04</span> Administration</NavLink>}
          <hr className="sidebar__rule" />
          <div className="sidebar__eyebrow">Pipeline</div>
          <div className="pipeline-mini"><i /><span><strong>Understand</strong><small>Project structure &amp; code analysis</small></span></div>
          <div className="pipeline-mini"><i /><span><strong>Detect issues</strong><small>Structure · quality · risk</small></span></div>
          <div className="pipeline-mini"><i /><span><strong>Repair &amp; validate</strong><small>Candidate → sandbox → evidence</small></span></div>
          <div className="pipeline-mini"><i /><span><strong>Report</strong><small>Findings · fixes · evidence</small></span></div>
        </aside>
        <main className="content"><Outlet /></main>
      </div>
    </div>
  );
}

function DashboardRoute() {
  const { history, result } = useWorkspace();
  const navigate = useNavigate();
  const canStartAnalysis = usePermission("createAnalysis");
  return <DashboardPage history={history} latestResult={result} onStart={() => navigate("/projects/new")} onOpenResults={() => result && navigate(`/reports/${encodeURIComponent(result.project_id)}`)} onOpenHistory={() => navigate("/history")} canStartAnalysis={canStartAnalysis} />;
}

function UploadRoute() {
  const { history, handleStart, openHistory } = useWorkspace();
  const [query] = useSearchParams();
  const existingProjectId = query.get("project") ?? undefined;
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [files, setFiles] = useState<ApiProjectFile[]>([]);
  const [projectLoadError, setProjectLoadError] = useState("");

  useEffect(() => {
    if (!existingProjectId) return undefined;
    const controller = new AbortController();
    void Promise.all([getProject(existingProjectId, controller.signal), getProjectFiles(existingProjectId, controller.signal)])
      .then(([metadata, content]) => { setProject(metadata); setFiles(content.files); })
      .catch((error: unknown) => { if (!controller.signal.aborted) setProjectLoadError(error instanceof Error ? error.message : "Project files could not be loaded."); });
    return () => controller.abort();
  }, [existingProjectId]);

  if (existingProjectId && !project && !projectLoadError) return <section className="page"><p>Loading project files...</p></section>;
  return <><UploadPage onStart={(inputFiles, tools, _securityTools, projectName, configuration, projectId) => { void handleStart(inputFiles, tools, [], projectName, configuration, projectId); }} history={history} onOpenHistory={openHistory} initialFiles={files} initialProjectName={project?.name} existingProjectId={existingProjectId} projectLoadError={projectLoadError} /><AgentStatusPanel activeStep={0} progressMessage="Ready to coordinate analysis" preview /><ToolStatusPanel quality={["Ruff", "Pylint", "Radon"]} /></>;
}

function AnalysisRoute() {
  const { activeStepIndex, progressMessage, errorMessage, result, originalFiles } = useWorkspace();
  return errorMessage
    ? <section className="page page--error"><h1>Analysis stopped</h1><p>{errorMessage}</p><details><summary>Details</summary><p>Check that the gateway and orchestrator are available, then retry.</p></details><Link className="btn" to="/projects/new">Try again</Link></section>
    : <><AnalysisPage activeStepIndex={activeStepIndex} progressMessage={progressMessage} /><AgentStatusPanel activeStep={activeStepIndex} progressMessage={progressMessage} /><AnalysisTabs result={result} files={originalFiles} /></>;
}

function FindingsRoute() {
  const { result, history } = useWorkspace();
  const navigate = useNavigate();
  const findings = result?.findings ?? history.flatMap((entry) => entry.result.findings);
  return <FindingsReviewPage findings={findings} onNewAnalysis={() => navigate("/projects/new")} />;
}

function ResultsRoute() {
  const { result, originalFiles, rerun } = useWorkspace();
  const { id } = useParams();
  if (!result) return <section className="page empty-state"><strong>Report data is not loaded in this browser session.</strong><span>{id ? `Run ${id} may be available through the report API.` : "Open a saved history item or start a new analysis."}</span><Link className="btn btn--primary" to="/history">Open history</Link></section>;
  return <ResultsPage originalFiles={originalFiles} result={result} onRerun={rerun} />;
}

function HistoryRoute() {
  const { history, openHistory } = useWorkspace();
  const navigate = useNavigate();
  return <RepairHistoryPage history={history} onOpen={openHistory} onNewAnalysis={() => navigate("/projects/new")} />;
}

interface UnavailablePageProps { readonly title: string; }
function UnavailablePage({ title }: Readonly<UnavailablePageProps>) {
  return <section className="page empty-state"><h1>{title}</h1><strong>This page is not connected to a backend API yet.</strong><span>It will be implemented in a later delivery phase; no success data is being fabricated.</span></section>;
}

function NotFoundPage() {
  return <section className="page page--error"><h1>Page not found</h1><p>The requested workspace page does not exist.</p><Link className="btn btn--primary" to="/">Return to dashboard</Link></section>;
}
