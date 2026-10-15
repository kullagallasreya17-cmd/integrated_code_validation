import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import type { RunHistoryEntry, WorkflowRunResponse } from "../types/finding";

interface DashboardPageProps {
  history: RunHistoryEntry[];
  latestResult: WorkflowRunResponse | null;
  onStart: () => void;
  onOpenResults: () => void;
  onOpenHistory: () => void;
  canStartAnalysis: boolean;
}

interface ServiceHealth {
  status: string;
  healthy: boolean;
  details?: Record<string, unknown>;
}

const AGENT_SUMMARY = [
  ["01", "Code analysis", "AST structure and dependencies", "orchestrator"],
  ["02", "Security", "SAST, secrets and CWE evidence", "security"],
  ["03", "Code quality", "Ruff, Pylint and Radon", "code_quality"],
  ["04", "Bug & resource", "Runtime and resource risks", "bug_resource"],
  ["05", "Fix & regenerate", "Targeted patches or full code", "repair"],
  ["06", "Validation", "Tests and acceptance checks", "validation"],
  ["07", "Report", "Recommendations and traceability", "report"],
] as const;

const AGENT_STATUS_CLASS: Record<string, string> = {
  Connected: "connected",
  "Orchestrator stage": "stage",
  "Not connected": "planned",
  "Not configured": "planned",
  "Unavailable": "planned",
};

function normalizeAgentStatus(key: string, serviceState?: ServiceHealth): string {
  if (key === "report") return "Orchestrator stage";
  if (!serviceState) return "Not connected";
  if (serviceState.healthy) return "Connected";
  if (serviceState.status === "not_configured") return "Not configured";
  if (serviceState.status === "unavailable") return "Unavailable";
  return "Not connected";
}

export function DashboardPage({ history, latestResult, onStart, onOpenResults, onOpenHistory, canStartAnalysis }: Readonly<DashboardPageProps>) {
  const [agentServices, setAgentServices] = useState<Record<string, ServiceHealth>>({});

  useEffect(() => {
    let active = true;

    async function loadAgentHealth() {
      try {
        const payload = await apiClient.get<{ services?: Record<string, ServiceHealth>; ready?: number; configured?: number }>('/api/system/agents');
        if (!active) return;
        setAgentServices(payload.services ?? {});
      } catch {
        if (!active) return;
        setAgentServices({});
      }
    }

    void loadAgentHealth();
    return () => { active = false; };
  }, []);

  const findings = latestResult?.findings ?? [];
  const highRisk = findings.filter((finding) => finding.severity === "high" || finding.severity === "critical").length;
  const connectedCount = AGENT_SUMMARY.filter(([ , , , key]) => key !== "report" && agentServices[key]?.healthy).length;
  const totalTrackedAgents = AGENT_SUMMARY.filter(([ , , , key]) => key !== "report").length;

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
        <div className="metric-card"><span>Pipeline readiness</span><strong>{connectedCount} / {totalTrackedAgents}</strong><small>Live agents connected</small></div>
      </div>

      <div className="dashboard-grid">
        <section className="dashboard-panel dashboard-panel--wide">
          <div className="section-label"><h2>Agent operating system</h2><span>7 agents · 1 orchestrator · 1 sandbox</span></div>
          <div className="agent-summary-grid">
            {AGENT_SUMMARY.map(([number, name, detail, key]) => {
              const status = normalizeAgentStatus(key, agentServices[key]);
              const statusClass = AGENT_STATUS_CLASS[status];
              return (
              <div className="agent-summary-card" key={number}>
                <span className="agent-summary-card__number">{number}</span>
                <div><strong>{name}</strong><small>{detail}</small></div>
                <b className={`agent-summary-card__status agent-summary-card__status--${statusClass}`}>{status}</b>
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
