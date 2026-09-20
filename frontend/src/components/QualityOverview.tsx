import type { Finding, QualitySummary } from "../types/finding";

interface QualityOverviewProps {
  summary?: QualitySummary;
  findings: Finding[];
}

export function QualityOverview({ summary, findings }: QualityOverviewProps) {
  const highCount = findings.filter((finding) => finding.severity === "high" || finding.severity === "critical").length;
  const complexityPassed = summary ? summary.complex_functions <= 3 : true;
  const gatePassed = highCount === 0 && complexityPassed;
  const tools = ["ruff", "pylint", "radon"];

  return (
    <section className="quality-overview">
      <div className="section-label"><h2>Code quality</h2><span>{summary ? `${summary.files_analyzed} files analyzed` : "Waiting for run"}</span></div>
      <div className="quality-overview__metrics">
        <div><strong>{summary?.total_findings ?? findings.length}</strong><small>Total findings</small></div>
        <div><strong>{summary?.complex_functions ?? 0}</strong><small>Complex functions</small></div>
        <div><strong>{summary?.warnings ?? 0}</strong><small>Warnings</small></div>
        <div><strong>{summary?.errors ?? highCount}</strong><small>Errors</small></div>
      </div>
      <div className="quality-overview__tools">
        {tools.map((tool) => <div key={tool}><span className="quality-tool__status">✓</span><strong>{tool}</strong><small>{summary?.by_tool[tool] ?? 0} findings</small></div>)}
      </div>
      <div className={`quality-gate quality-gate--${gatePassed ? "passed" : "failed"}`}>
        <div><span className="quality-gate__eyebrow">Quality gate</span><strong>{gatePassed ? "PASSED" : "REVIEW REQUIRED"}</strong></div>
        <ul><li>{highCount === 0 ? "No high or critical issues" : `${highCount} high-risk issues detected`}</li><li>{complexityPassed ? "Complexity within threshold" : "Complexity threshold exceeded"}</li><li>Ruff, Pylint, and Radon results collected</li></ul>
      </div>
    </section>
  );
}
