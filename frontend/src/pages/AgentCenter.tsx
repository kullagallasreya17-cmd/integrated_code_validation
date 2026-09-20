const AGENTS = [
  { number: "01", name: "Code Analysis Agent", role: "Understands the project", status: "Connected", output: "AST structure · dependencies · code context", color: "teal" },
  { number: "02", name: "Security Agent", role: "Finds security risk", status: "Integration point", output: "SAST · secrets · OWASP/CWE mapping", color: "amber" },
  { number: "03", name: "Code Quality Agent", role: "Measures maintainability", status: "Connected", output: "Ruff · Pylint · Radon findings", color: "teal" },
  { number: "04", name: "Bug & Resource Agent", role: "Identifies runtime risk", status: "Integration point", output: "Logic · performance · resource evidence", color: "blue" },
  { number: "05", name: "Fix & Regeneration Agent", role: "Creates repair candidates", status: "Integration point", output: "Targeted patch · full regeneration", color: "blue" },
  { number: "06", name: "Validation Agent", role: "Verifies acceptance", status: "Integration point", output: "Tests · scans · pass/fail evidence", color: "amber" },
  { number: "07", name: "Report Agent", role: "Makes the result traceable", status: "Integration point", output: "Explanation · recommendations · report", color: "teal" },
];

export function AgentCenter() {
  return (
    <section className="page agent-center-page">
      <div className="page-heading">
        <div><div className="kicker">Agent control room <span>Architecture view</span></div><h1>One graph.<br /><em>Seven minds.</em></h1><p>Every specialist contributes evidence to the orchestrator. The sandbox remains an execution boundary, never an agent.</p></div>
        <div className="heading-stamp"><span>7×</span><strong>Specialist<br />agents</strong></div>
      </div>

      <section className="orchestrator-rail">
        <div className="orchestrator-rail__node"><span className="orchestrator-rail__pulse" /><div><strong>LangGraph Orchestrator</strong><small>State, routing, retry limits and final acceptance</small></div><b>ACTIVE</b></div>
        <div className="orchestrator-rail__line" />
        <div className="orchestrator-rail__node orchestrator-rail__node--sandbox"><span className="orchestrator-rail__pulse" /><div><strong>Docker Sandbox</strong><small>Isolated execution · timeout · captured evidence</small></div><b>BOUNDARY</b></div>
      </section>

      <div className="agent-center-grid">
        {AGENTS.map((agent) => <article className={`agent-detail-card agent-detail-card--${agent.color}`} key={agent.number}><div className="agent-detail-card__top"><span>{agent.number}</span><b>{agent.status}</b></div><h2>{agent.name}</h2><p>{agent.role}</p><div className="agent-detail-card__output"><small>Produces</small><strong>{agent.output}</strong></div></article>)}
      </div>

      <section className="workflow-contract">
        <div><span className="kicker">Workflow contract</span><h2>Evidence moves forward.<br />Failures move back.</h2></div>
        <div className="workflow-contract__steps"><span>Understand</span><i>→</i><span>Analyze</span><i>→</i><span>Repair</span><i>→</i><span>Validate</span><i>→</i><span>Report</span></div>
      </section>
    </section>
  );
}
