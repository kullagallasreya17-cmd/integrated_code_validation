import { useState } from "react";
import { FindingsTable } from "../components/FindingsTable";
import { CodeComparison } from "../components/CodeComparison";
import { ValidationResult } from "../components/ValidationResult";
import { CodeEditor } from "../components/CodeEditor";
import { QualityOverview } from "../components/QualityOverview";
import type { Finding, ProjectFile, WorkflowRunResponse } from "../types/finding";

interface ResultsPageProps {
  originalFiles: ProjectFile[];
  result: WorkflowRunResponse;
  onRerun: () => void;
}

export function ResultsPage({ originalFiles, result, onRerun }: ResultsPageProps) {
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null);
  const repairedFiles: ProjectFile[] = Object.entries(
    (result.final_report as unknown as { final_code?: Record<string, string> }).final_code ?? {}
  ).map(([path, content]) => ({ path, content }));
  const quality = result.final_report.quality_summary;
  const reanalysis = result.final_report.reanalysis_summary;
  const comparison = result.final_report.comparison;

  return (
    <section className="page page--results">
      <div className="results-header">
        <div><div className="kicker">Run complete <span>04 / 04</span></div><h1>Analysis<br /><em>report.</em></h1><p>{result.project_id} · evidence collected from the validation pipeline</p></div>
        <div className="results-actions">
        <button className="btn btn--primary" onClick={onRerun}>
          Re-run analysis <span>↗</span>
        </button>
        <button
          className="btn"
          onClick={() => {
            const blob = new Blob([JSON.stringify(result.final_report, null, 2)], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = `${result.project_id}-report.json`;
            link.click();
            URL.revokeObjectURL(url);
          }}
        >
            Download report ↓
        </button>
          </div>
      </div>

        <div className="result-overview">
          <div className="summary-card summary-card--main"><span className="summary-card__label">Validation status</span><strong>{result.validation_status}</strong><small>{result.retry_count} repair retries used</small></div>
          <div className="summary-card"><span className="summary-card__label">Total findings</span><strong>{result.findings.length}</strong><small>across submitted files</small></div>
          <div className="summary-card"><span className="summary-card__label">High risk</span><strong>{result.findings.filter((f) => f.severity === "high" || f.severity === "critical").length}</strong><small>needs attention</small></div>
          <div className="summary-card"><span className="summary-card__label">Files scanned</span><strong>{originalFiles.length}</strong><small>Python sources</small></div>
        </div>

      <QualityOverview summary={quality} findings={result.findings} />

      {comparison && <section className="quality-summary comparison-summary"><div className="section-label"><h2>Re-analysis comparison</h2><span>{comparison.improved ? "Quality improved" : "No improvement detected"}</span></div><div className="comparison-strip"><div><strong>{quality?.total_findings ?? comparison.findings_before}</strong><small>Before</small></div><span>→</span><div><strong>{reanalysis?.total_findings ?? comparison.findings_after}</strong><small>After</small></div><div className="comparison-resolved"><strong>{comparison.resolved_issues.length}</strong><small>Resolved issues</small></div><div><strong>{comparison.changed_files.length}</strong><small>Changed files</small></div></div></section>}

      <ValidationResult report={result.final_report} />

        <section className="result-section"><h2>Findings <span className="section-label span">{result.findings.length} recorded</span></h2><FindingsTable findings={result.findings} onSelect={setSelectedFinding} /></section>

      {selectedFinding && (() => {
        const selectedFile = originalFiles.find((file) => file.path === selectedFinding.file);
        return selectedFile ? <section className="result-section finding-inspector"><div className="section-label"><h2>Finding in context</h2><span>{selectedFinding.tool ?? "analysis"} · line {selectedFinding.line_number ?? "-"}</span></div><div className="finding-inspector__summary"><strong>{selectedFinding.issue}</strong><span>{selectedFinding.description}</span></div><CodeEditor key={`${selectedFinding.finding_id}-${selectedFinding.line_number}`} path={selectedFile.path} value={selectedFile.content} readOnly highlightLine={selectedFinding.line_number} height="300px" /></section> : null;
      })()}

      {repairedFiles.length > 0 && (
          <section className="result-section">
          <h2>Original vs. repaired code</h2>
          <CodeComparison original={originalFiles} repaired={repairedFiles} />
          </section>
      )}
    </section>
  );
}
