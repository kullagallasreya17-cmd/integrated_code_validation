const AGENTS = [
  { number: "01", name: "Code Analysis Agent", role: "Understands the project", status: "Connected", output: "AST structure · dependencies · code context", color: "teal" },
  { number: "02", name: "Security Agent", role: "Finds security risk", status: "Not deployed", output: "SAST · secrets · OWASP/CWE mapping", color: "amber" },
  { number: "03", name: "Code Quality Agent", role: "Measures maintainability", status: "Connected", output: "Ruff · Pylint · Radon findings", color: "teal" },
  { number: "04", name: "Bug & Resource Agent", role: "Identifies runtime risk", status: "Not deployed", output: "Logic · performance · resource evidence", color: "blue" },
  { number: "05", name: "Fix & Regeneration Agent", role: "Creates repair candidates", status: "Not deployed", output: "Targeted patch · full regeneration", color: "blue" },
  { number: "06", name: "Validation Agent", role: "Verifies acceptance", status: "Not deployed", output: "Tests · scans · pass/fail evidence", color: "amber" },
  { number: "07", name: "Report Agent", role: "Makes the result traceable", status: "Orchestrator stage", output: "Explanation · recommendations · report", color: "teal" },
];

export function AgentCenter() {
  return (
    <section className="page agent-center-page">
      <div className="page-heading">
        <div><div className="kicker">Agent control room <span>Deployment view</span></div><h1>Know what’s<br /><em>connected.</em></h1><p>This stack connects code analysis and code quality. Security, bug/resource, repair, validation, and sandbox services are not deployed here.</p></div>
        <div className="heading-stamp"><span>2×</span><strong>Connected<br />specialists</strong></div>
      </div>

      <section className="orchestrator-rail">
        <div className="orchestrator-rail__node"><span className="orchestrator-rail__pulse" /><div><strong>LangGraph Orchestrator</strong><small>State, routing, retry limits and final acceptance</small></div><b>ACTIVE</b></div>
        <div className="orchestrator-rail__line" />
        <div className="orchestrator-rail__node orchestrator-rail__node--sandbox"><span className="orchestrator-rail__pulse" /><div><strong>Docker Sandbox</strong><small>Execution service is not present in this Compose stack</small></div><b>NOT DEPLOYED</b></div>
      </section>

      <div className="agent-center-grid">
        {AGENTS.map((agent) => <article className={`agent-detail-card agent-detail-card--${agent.color}`} key={agent.number}><div className="agent-detail-card__top"><span>{agent.number}</span><b>{agent.status}</b></div><h2>{agent.name}</h2><p>{agent.role}</p><div className="agent-detail-card__output"><small>Produces</small><strong>{agent.output}</strong></div></article>)}
      </div>

      <section className="workflow-contract">
        <div><span className="kicker">Workflow design</span><h2>Configured stages depend<br />on connected services.</h2></div>
        <div className="workflow-contract__steps"><span>Understand</span><i>→</i><span>Analyze</span><i>→</i><span>Repair</span><i>→</i><span>Validate</span><i>→</i><span>Report</span></div>
      </section>
    </section>
  );
}
