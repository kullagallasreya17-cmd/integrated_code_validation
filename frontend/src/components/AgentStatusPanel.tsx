interface AgentStatusPanelProps {
  activeStep: number;
  progressMessage?: string;
  validationStatus?: string;
  preview?: boolean;
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

const AGENT_BY_WORKFLOW_STEP: Record<number, number> = {
  0: 0,
  1: 2,
  3: 6,
  4: 6,
  5: 4,
  6: 5,
  7: 2,
  8: 5,
  9: 6,
};

export function AgentStatusPanel({ activeStep, progressMessage, validationStatus, preview = false }: AgentStatusPanelProps) {
  return (
    <div className="agent-panel">
      <div className="agent-panel__header"><span className="kicker">A2A / workflow view</span><span className="agent-panel__pulse"><i /> {progressMessage ?? "Waiting for workflow"}</span></div>
      <div className="agent-grid">
        {AGENTS.map(([key, label], index) => {
          const activeAgentIndex = AGENT_BY_WORKFLOW_STEP[activeStep] ?? 0;
          const status = preview
            ? (index === 0 ? "completed" : "pending")
            : index < activeAgentIndex ? "completed" : index === activeAgentIndex ? "running" : "pending";
          return <div className={`agent-card agent-card--${status}`} key={key}><span className="agent-card__index">0{index + 1}</span><span><strong>{label}</strong><small>{status}</small></span><b>{status === "completed" ? "✓" : status === "running" ? "●" : "○"}</b></div>;
        })}
      </div>
      {!preview && (activeStep === 1 || activeStep === 7) && <div className="quality-live"><div><strong>Code Quality Agent</strong><small>Ruff · Pylint · Radon</small></div><span><i /> running</span></div>}
      {validationStatus && <div className={`workflow-outcome workflow-outcome--${validationStatus}`}><span>{validationStatus === "passed" ? "PASS" : validationStatus === "failed" ? "FAIL" : "PENDING"}</span><small>Validation outcome</small></div>}
    </div>
  );
}