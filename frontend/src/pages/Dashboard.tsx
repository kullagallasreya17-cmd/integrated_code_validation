import type { RunHistoryEntry, WorkflowRunResponse } from "../types/finding";

interface DashboardPageProps {
  history: RunHistoryEntry[];
  latestResult: WorkflowRunResponse | null;
  onStart: () => void;
  onOpenResults: () => void;
  onOpenHistory: () => void;
  canStartAnalysis: boolean;
}

const AGENT_SUMMARY = [
  ["01", "Code analysis", "AST structure and dependencies", "Ready"],
  ["02", "Security", "SAST, secrets and CWE evidence", "Planned"],
  ["03", "Code quality", "Ruff, Pylint and Radon", "Ready"],
  ["04", "Bug & resource", "Runtime and resource risks", "Planned"],
  ["05", "Fix & regenerate", "Targeted patches or full code", "Planned"],
  ["06", "Validation", "Tests and acceptance checks", "Planned"],
  ["07", "Report", "Recommendations and traceability", "Planned"],
];

export function DashboardPage({ history, latestResult, onStart, onOpenResults, onOpenHistory, canStartAnalysis }: Readonly<DashboardPageProps>) {
  const findings = latestResult?.findings ?? [];
  const highRisk = findings.filter((finding) => finding.severity === "high" || finding.severity === "critical").length;
  const passed = latestResult?.validation_status === "passed";
  const agentStatus = latestResult
    ? ["COMPLETED", "WAITING", "COMPLETED", "WAITING", latestResult.retry_count > 0 ? "COMPLETED" : "WAITING", latestResult.validation_status === "passed" ? "COMPLETED" : "WAITING", "COMPLETED"]
    : ["READY", "WAITING", "READY", "WAITING", "WAITING", "WAITING", "WAITING"];

  return (
    <section className="page dashboard-page">
      <div className="dashboard-hero">
        <div>
          <div className="kicker">Workspace overview <span>00 / 04</span></div>
          <h1>Ship code<br /><em>with evidence.</em></h1>
          <p>One controlled workflow for understanding Python projects, reviewing risk, and validating every repair candidate.</p>
        </div>
        {canStartAnalysis && <button className="btn btn--primary dashboard-hero__cta" onClick={onStart}>Start an analysis <span>↗</span></button>}
      </div>

      <div className="metric-grid">
        <div className="metric-card metric-card--accent"><span>Latest decision</span><strong>{latestResult ? latestResult.validation_status : "Not run"}</strong><small>{latestResult ? latestResult.project_id : "Submit a project to begin"}</small></div>
        <div className="metric-card"><span>Findings to review</span><strong>{findings.length}</strong><small>{highRisk} high or critical</small></div>
        <div className="metric-card"><span>Runs in workspace</span><strong>{history.length}</strong><small>Stored locally for this session</small></div>
        <div className="metric-card"><span>Pipeline readiness</span><strong>{passed ? "Accepted" : "3 / 7"}</strong><small>{passed ? "Validation criteria met" : "Core agents connected"}</small></div>
      </div>

      <div className="dashboard-grid">
        <section className="dashboard-panel dashboard-panel--wide">
          <div className="section-label"><h2>Agent operating system</h2><span>7 agents · 1 orchestrator · 1 sandbox</span></div>
          <div className="agent-summary-grid">
            {AGENT_SUMMARY.map(([number, name, detail], index) => {
              const status = agentStatus[index];
              return (
              <div className="agent-summary-card" key={number}>
                <span className="agent-summary-card__number">{number}</span>
                <div><strong>{name}</strong><small>{detail}</small></div>
                <b className={`agent-summary-card__status agent-summary-card__status--${status.toLowerCase()}`}><i />{status}</b>
              </div>
              );
            })}
          </div>
        </section>

        <section className="dashboard-panel">
          <div className="section-label"><h2>Latest run</h2><span>{latestResult ? "Available" : "Waiting"}</span></div>
          {latestResult ? (
            <div className="latest-run">
              <strong>{latestResult.project_id}</strong>
              <span className={`run-decision run-decision--${latestResult.validation_status}`}>{latestResult.validation_status}</span>
              <p>{findings.length} findings · {latestResult.retry_count} repair retries</p>
              <button className="btn btn--link" onClick={onOpenResults}>Open report <span>↗</span></button>
            </div>
          ) : (
            <div className="dashboard-empty"><strong>No analysis yet</strong><span>Your first run will appear here with its decision, evidence, and repair history.</span>{canStartAnalysis && <button className="btn btn--secondary" onClick={onStart}>Create first run</button>}</div>
          )}
        </section>

        <section className="dashboard-panel">
          <div className="section-label"><h2>Recent activity</h2><span>{history.length} runs</span></div>
          {history.length > 0 ? <div className="activity-list">{history.slice(0, 4).map((entry) => <button className="activity-row" key={`${entry.project_id}-${entry.timestamp}`} onClick={onOpenHistory}><span className="activity-row__dot" /><span><strong>{entry.project_id}</strong><small>{new Date(entry.timestamp).toLocaleString()}</small></span><b>{entry.validation_status}</b></button>)}</div> : <div className="dashboard-empty"><strong>Activity is clear</strong><span>Completed analyses and validation events will be listed here.</span><button className="btn btn--link" onClick={onOpenHistory}>View history <span>↗</span></button></div>}
        </section>
      </div>
    </section>
  );
}
