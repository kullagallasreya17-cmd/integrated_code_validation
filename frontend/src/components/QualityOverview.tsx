import type { Finding, QualitySummary } from "../types/finding";
import { safeEvidence } from "../analysis/model";

interface QualityOverviewProps {
  summary?: QualitySummary;
  findings: Finding[];
}

function toolRunSymbol(status: string | undefined): string {
  if (status === undefined) return "-";
  if (status === "completed") return "✓";
  return "!";
}

export function QualityOverview({ summary, findings }: Readonly<QualityOverviewProps>) {
  const highCount = findings.filter((finding) => finding.severity === "high" || finding.severity === "critical").length;
  const gateStatus = summary?.quality_gate_status ?? summary?.quality_gate?.status;
  const gatePassed = gateStatus === "PASS";
  const complexityPassed = summary ? summary.complex_functions <= (summary.quality_gate?.thresholds.complexity_limit ?? 3) : true;
  const tools = ["ruff", "pylint", "radon"];

  return (
    <section className="quality-overview">
      <div className="section-label"><h2>Code quality</h2><span>{summary ? `${summary.files_analyzed} files analyzed` : "Waiting for run"}</span></div>
      <div className="quality-overview__metrics">
        <div><strong>{summary?.quality_score ?? "-"}</strong><small>Quality score</small></div>
        <div><strong>{summary?.total_findings ?? findings.length}</strong><small>Total findings</small></div>
        <div><strong>{summary?.complex_functions ?? 0}</strong><small>Complex functions</small></div>
        <div><strong>{summary?.warnings ?? 0}</strong><small>Warnings</small></div>
        <div><strong>{summary?.errors ?? highCount}</strong><small>Errors</small></div>
      </div>
      <div className="quality-overview__tools">
        {tools.map((tool) => {
          const run = summary?.tool_runs?.find((item) => item.tool === tool);
          return <div key={tool}><span className="quality-tool__status">{toolRunSymbol(run?.status)}</span><strong>{tool}</strong><small>{run ? `${run.finding_count} findings` : "not run"}</small></div>;
        })}
      </div>
      <div className={`quality-gate quality-gate--${gatePassed ? "passed" : "failed"}`}>
        <div><span className="quality-gate__eyebrow">Quality gate</span><strong>{gateStatus ?? "NOT AVAILABLE"}</strong></div>
        <ul><li>{summary ? `${summary.errors} errors and ${summary.warnings} warnings` : `${highCount} high-risk issues detected`}</li><li>{complexityPassed ? "Complexity within threshold" : "Complexity threshold exceeded"}</li><li>{summary?.quality_gate ? `Minimum score: ${summary.quality_gate.thresholds.minimum_score}` : "Waiting for quality analysis"}</li></ul>
      </div>
      {summary?.hotspots && summary.hotspots.length > 0 && <div className="quality-overview__hotspots"><span className="quality-gate__eyebrow">Complexity hotspots</span>{summary.hotspots.slice(0, 3).map((hotspot) => <div key={`${hotspot.file}-${hotspot.line}-${hotspot.function_name}`}><strong>{safeEvidence(hotspot.function_name)}</strong><small>{safeEvidence(hotspot.file ?? "-")}:{hotspot.line ?? "-"} · complexity {hotspot.complexity} · {safeEvidence(hotspot.risk_level)} risk</small></div>)}</div>}
    </section>
  );
}
