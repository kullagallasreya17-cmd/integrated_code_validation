import type { WorkflowRunResponse } from "../types/finding";
import type { AnalysisCheckOptions } from "../api/configuration";

interface AgentStatusPanelProps {
  workflowStep: string;
  workflowStatus: string;
  progressMessage?: string;
  preview?: boolean;
  result?: WorkflowRunResponse | null;
  analysisChecks?: AnalysisCheckOptions;
}

const AGENTS = [
  ["analysis", "Code Analysis Agent"],
  ["security", "Security Agent"],
  ["quality", "Code Quality Agent"],
  ["resource", "Bug & Resource Agent"],
  ["repair", "Fix & Regeneration Agent"],
  ["validation", "Validation Agent"],
  ["report", "Report Agent"],
];

type AgentCardStatus = "completed" | "running" | "pending" | "failed" | "skipped" | "not reported";

const STATUS_SYMBOL: Record<AgentCardStatus, string> = {
  completed: "✓",
  running: "●",
  pending: "○",
  failed: "!",
  skipped: "–",
  "not reported": "-",
};

const STAGE_AGENTS: Record<string, string[]> = {
  understand: ["analysis"],
  analyze: ["security", "quality", "resource"],
  reanalyze: ["quality"],
  repair: ["repair"],
  validate: ["validation"],
  finalize: ["report"],
};

const AGENT_ERRORS: Record<string, string[]> = {
  analysis: ["analysis", "understand"],
  security: ["security"],
  quality: ["quality"],
  resource: ["bug_resource", "resource"],
  repair: ["repair"],
  validation: ["validation", "sandbox"],
  report: ["report", "finalize"],
}

const STAGE_ORDER = ["understand", "analyze", "aggregate", "explain_prioritize", "repair", "validate", "reanalyze", "compare", "finalize"];

function textField(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function reportedAgentStatus(key: string, result: WorkflowRunResponse): AgentCardStatus {
  const report = result.final_report;
  const configuredChecks = report.analysis_checks;
  if (key === "security" && configuredChecks?.security === false) return "skipped";
  if (key === "quality" && configuredChecks?.code_quality === false && configuredChecks?.complexity === false) return "skipped";
  if (key === "resource" && configuredChecks?.bug_resource === false) return "skipped";
  if (key === "repair" && configuredChecks?.automated_repair === false) return "skipped";
  if (key === "validation" && configuredChecks?.final_validation === false) return "skipped";
  const errors = [...(report.agent_errors ?? []), ...(report.workflow_summary?.agent_failures ?? [])];
  if (errors.some((item) => AGENT_ERRORS[key].some((name) => item.agent.toLowerCase().includes(name)))) return "failed";
  const stages = report.stage_history ?? [];
  const analysisStage = [...stages].reverse().find((stage) => stage.stage === "analyze");
  const analysisAgentStatus = textField((analysisStage?.agents as Record<string, unknown> | undefined)?.[key === "resource" ? "bug_resource" : key]);
  if (analysisAgentStatus === "skipped") return "skipped";
  if (analysisAgentStatus === "failed") return "failed";
  if (analysisAgentStatus === "completed") return "completed";
  const relevant = stages.filter((stage) => STAGE_AGENTS[textField(stage.stage) ?? ""]?.includes(key));
  const latest = relevant[relevant.length - 1];
  if (!latest) return "not reported";
  const status = textField(latest.status);
  if (status === "skipped") return "skipped";
  if (status === "failed") return "failed";
  if (["completed", "passed", "partial"].includes(status ?? "")) return "completed";
  return "not reported";
}

function liveAgentStatus(key: string, step: string, status: string, checks?: AnalysisCheckOptions): AgentCardStatus {
  if (checks && ((key === "security" && !checks.security)
    || (key === "quality" && !checks.codeQuality && !checks.complexity)
    || (key === "resource" && !checks.bugResource)
    || (key === "repair" && !checks.automatedRepair)
    || (key === "validation" && !checks.finalValidation))) return "skipped";
  const rank = STAGE_ORDER.indexOf(step);
  const assignedStages = Object.entries(STAGE_AGENTS).filter(([, agentKeys]) => agentKeys.includes(key)).map(([stage]) => stage);
  if (status === "failed") return assignedStages.includes(step) ? "failed" : "pending";
  if (status !== "working" && status !== "submitted" && status !== "queued") return "pending";
  if (rank < 0) return "not reported";
  const assignedRank = Math.min(...assignedStages.map((stage) => STAGE_ORDER.indexOf(stage)));
  if (step === "reanalyze" && key === "quality") return "running";
  if (assignedRank < rank) return "completed";
  if (assignedStages.includes(step)) return "running";
  return "pending";
}

function getAgentCardStatus(preview: boolean, result: WorkflowRunResponse | null | undefined, key: string, step: string, status: string, checks?: AnalysisCheckOptions): AgentCardStatus {
  if (preview) return liveAgentStatus(key, step, status, checks) === "skipped" ? "skipped" : "pending";
  if (result) return reportedAgentStatus(key, result);
  return liveAgentStatus(key, step, status, checks);
}

export function AgentStatusPanel({ workflowStep, workflowStatus, progressMessage, preview = false, result, analysisChecks }: Readonly<AgentStatusPanelProps>) {
  return (
    <div className="agent-panel">
      <div className="agent-panel__header"><span className="kicker">A2A / workflow view · {workflowStatus}</span><span className="agent-panel__pulse"><i /> {progressMessage ?? "Waiting for workflow"}</span></div>
      <div className="agent-grid">
        {AGENTS.map(([key, label], index) => {
          const agentKey = String(key);
          const status = getAgentCardStatus(preview, result, agentKey, workflowStep, workflowStatus, analysisChecks);
          return <div className={`agent-card agent-card--${status.replace(" ", "-")}`} key={agentKey}><span className="agent-card__index">0{index + 1}</span><span><strong>{label}</strong><small>{status}</small></span><b>{STATUS_SYMBOL[status]}</b></div>;
        })}
      </div>
      {result && <div className={`workflow-outcome workflow-outcome--${result.validation_status}`}><span>{result.validation_status.toUpperCase()}</span><small>Validation outcome · {result.retry_count} repair retries</small></div>}
    </div>
  );
}