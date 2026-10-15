import { useMemo, useState } from "react";
import { numberOf, recordOf, safeEvidence, textOf } from "./model";
import type { FinalReport, Finding, ProjectFile, QualitySummary, Severity, WorkflowRunResponse } from "../types/finding";

interface AnalysisReportProps {
  readonly result: WorkflowRunResponse;
  readonly sourceFiles: ProjectFile[];
  readonly completedAt?: string;
  readonly onViewFile: (path: string) => void;
}

const SEVERITIES: Severity[] = ["critical", "high", "medium", "low"];
const TOOLS = ["ruff", "pylint", "radon"];
const TOOL_CODE_PATTERN = /\b[A-Z][A-Z0-9]{0,16}\d{3,}\b/;
const PIPELINE = [
  { label: "Understand", keys: ["understand"] },
  { label: "Analyze", keys: ["analyze"] },
  { label: "Aggregate", keys: ["aggregate"] },
  { label: "Prioritize", keys: ["explainprioritize", "prioritize"] },
  { label: "AI report & recommendations", keys: ["reportrecommend"] },
  { label: "Repair", keys: ["repair"] },
  { label: "Validate", keys: ["validate"] },
  { label: "Re-analyze", keys: ["reanalyze", "reanalyzecode"] },
  { label: "Compare", keys: ["compare"] },
  { label: "Report", keys: ["finalize", "report"] },
];

type FileMetrics = NonNullable<QualitySummary["per_file"]>[string];

interface ReportFileRow {
  readonly path: string;
  readonly source?: ProjectFile;
  readonly findings: Finding[];
  readonly metrics?: FileMetrics;
}

function toList(value: unknown): Record<string, unknown>[] | undefined {
  return Array.isArray(value) ? value.filter((item) => item !== null && typeof item === "object") as Record<string, unknown>[] : undefined;
}

function toFindings(value: unknown): Finding[] | undefined {
  return Array.isArray(value) ? value as Finding[] : undefined;
}

function display(value: string | number | undefined): string {
  return value === undefined || value === "" ? "Not available" : String(value);
}

function safeText(value: unknown): string | undefined {
  if (typeof value === "string" && value.trim()) return safeEvidence(value);
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return undefined;
}

function severityCounts(findings: Finding[]): Record<Severity, number> {
  return {
    critical: findings.filter((finding) => finding.severity === "critical").length,
    high: findings.filter((finding) => finding.severity === "high").length,
    medium: findings.filter((finding) => finding.severity === "medium").length,
    low: findings.filter((finding) => finding.severity === "low").length,
    info: findings.filter((finding) => finding.severity === "info").length,
  };
}

function validationLabel(status: string): string {
  if (status === "passed") return "PASSED";
  if (status === "failed") return "FAILED";
  if (status === "not_run") return "NOT RUN";
  if (status === "pending" || status === "in_progress") return "IN PROGRESS";
  return "NOT AVAILABLE";
}

function validationClass(status: string): string {
  if (status === "passed") return "passed";
  if (status === "failed") return "failed";
  if (status === "pending" || status === "in_progress") return "progress";
  return "unknown";
}

function stageKey(value: unknown): string {
  return typeof value === "string" ? value.toLowerCase().replace(/[^a-z]/g, "") : "";
}

function stageStatusLabel(value: unknown): string {
  if (typeof value !== "string") return "Not reported";
  const status = value.toLowerCase().replace(/[ -]/g, "_");
  if (status === "completed" || status === "complete" || status === "passed" || status === "pass") return "Completed";
  if (status === "skipped" || status === "not_required") return "Skipped";
  if (status === "failed" || status === "error") return "Failed";
  if (status === "working" || status === "running" || status === "in_progress" || status === "started") return "In progress";
  if (status === "partial") return "Partial";
  return "Not reported";
}

function stageStatusClass(label: string): string {
  if (label === "Completed") return "completed";
  if (label === "Skipped") return "skipped";
  if (label === "Failed") return "failed";
  if (label === "In progress") return "progress";
  if (label === "Partial") return "partial";
  return "unknown";
}

function formatDate(value?: string): string {
  if (!value) return "Not available";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not available" : date.toLocaleString();
}

function findingCode(finding: Finding): string {
  const toolCode = TOOL_CODE_PATTERN.exec(finding.issue);
  return toolCode?.[0] ?? finding.issue;
}

function validationExplanation(status: string, findingCount: number, reasons: string[], counts: Record<Severity, number | undefined>): string {
  if (status === "passed") {
    if (findingCount === 0) return "Validation passed and no findings were returned.";
    const suffix = findingCount === 1 ? "" : "s";
    return `Validation passed with ${findingCount} finding${suffix} returned for review.`;
  }
  if (status === "failed") {
    if (reasons[0]) return `Validation did not pass because the workflow reported: ${reasons[0]}`;
    const criticalOrHigh = (counts.critical ?? 0) + (counts.high ?? 0);
    if (criticalOrHigh > 0) {
      const suffix = criticalOrHigh === 1 ? "" : "s";
      return `Validation failed with ${counts.critical} critical and ${counts.high} high-severity finding${suffix}.`;
    }
    return "The workflow reported a failed validation. No specific validation error was returned.";
  }
  if (status === "pending") return "This workflow is still in progress; a final validation decision has not been returned.";
  if (status === "not_run") return "Final validation was not run for this analysis. Review the available analyzer results.";
  return "The workflow did not return a validation explanation.";
}

function validationHeading(status: string): string {
  if (status === "not_run") return "Validation not run";
  if (status === "passed") return "Why did validation pass?";
  if (status === "failed") return "Why did validation fail?";
  return "Why did validation stop?";
}

function toolStatusClass(status: string): string {
  if (status === "Completed" || status === "Passed") return "completed";
  if (status === "Failed") return "failed";
  return "unknown";
}

function availabilityMessage(agent: string, error: { message: string } | undefined, reported: boolean, count: number): string {
  if (error) return `Not analyzed: ${error.message}`;
  if (!reported) return `${agent} analysis was not run or its results were not returned for this validation.`;
  const suffix = count === 1 ? "" : "s";
  return `${count} ${agent.toLowerCase()} finding${suffix} returned.`;
}

function findingSummary(hasFindingData: boolean, findings: Finding[]): string {
  if (!hasFindingData) return "Finding data not returned";
  const suffix = findings.length === 1 ? "" : "s";
  return `${findings.length} finding${suffix} returned`;
}

function recommendationStatusLabel(status: string): string {
  if (status === "passed") return "REVIEW RESULTS";
  if (status === "failed") return "REVIEW REQUIRED";
  return validationLabel(status);
}

function getFindingData(result: WorkflowRunResponse, report: FinalReport, rawReport: Record<string, unknown>) {
  const findings = toFindings(result.findings) ?? toFindings(rawReport.findings) ?? [];
  const hasFindingData = result.findings_reported ?? (Array.isArray(result.findings) || Array.isArray(rawReport.findings));
  const bySeverity = recordOf(recordOf(report.findings_summary).by_severity);
  const counts = hasFindingData ? severityCounts(findings) : {
    critical: numberOf(bySeverity.critical),
    high: numberOf(bySeverity.high),
    medium: numberOf(bySeverity.medium),
    low: numberOf(bySeverity.low),
    info: numberOf(bySeverity.info),
  };
  return { findings, hasFindingData, counts };
}

function getAgentData(result: WorkflowRunResponse, report: FinalReport, rawReport: Record<string, unknown>, findings: Finding[]) {
  const errors = toList(result.agent_errors) ?? toList(report.agent_errors) ?? [];
  const errorSummary = errors.map((error) => ({
    agent: safeText(error.agent) ?? "Agent",
    message: safeText(error.error) ?? "Error detail not available",
  }));
  const findError = (names: string[]) => errorSummary.find((error) => names.some((name) => error.agent.toLowerCase().includes(name)));
  const securityFindings = toFindings(result.security_findings) ?? toFindings(report.security_findings) ?? findings.filter((finding) => finding.category === "security");
  const resourceFindings = toFindings(result.resource_findings) ?? toFindings(report.resource_findings) ?? findings.filter((finding) => finding.category === "resource" || finding.category === "bug");
  const securityError = findError(["security"]);
  const resourceError = findError(["bug", "resource"]);
  const securityReported = !securityError && (Array.isArray(result.security_findings) || Array.isArray(report.security_findings) || findings.some((finding) => finding.category === "security"));
  const resourceReported = !resourceError && (Array.isArray(result.resource_findings) || Array.isArray(report.resource_findings) || findings.some((finding) => finding.category === "resource" || finding.category === "bug"));
  return {
    errors,
    errorSummary,
    securityFindings,
    resourceFindings,
    securityError,
    resourceError,
    securityReported,
    resourceReported,
    securityTools: toList(result.security_tool_runs) ?? toList(rawReport.security_tool_runs) ?? [],
  };
}

function buildFileRows(sourceFiles: ProjectFile[], perFile: Record<string, FileMetrics | undefined>, findings: Finding[]): ReportFileRow[] {
  const paths = new Set([
    ...sourceFiles.map((file) => file.path),
    ...Object.keys(perFile),
    ...findings.map((finding) => finding.file),
  ]);
  return [...paths].sort((first, second) => first.localeCompare(second)).map((path) => ({
    path,
    source: sourceFiles.find((file) => file.path === path),
    findings: findings.filter((finding) => finding.file === path),
    metrics: perFile[path],
  }));
}

function buildRecommendations(report: FinalReport, findings: Finding[]): string[] {
  const reportRecommendations = Array.isArray(report.recommendations)
    ? report.recommendations.filter((item): item is string => typeof item === "string")
    : [];
  return [...reportRecommendations, ...findings.map((finding) => finding.recommendation).filter((item): item is string => Boolean(item))]
    .filter((recommendation, index, values) => values.indexOf(recommendation) === index);
}

function buildComparisonData(comparison: Record<string, unknown>, quality: QualitySummary | undefined, reanalysis: QualitySummary | undefined) {
  const hasReanalysis = Boolean(reanalysis && Object.keys(reanalysis).length > 0);
  const beforeScore = numberOf(comparison.quality_score_before) ?? (hasReanalysis ? numberOf(quality?.quality_score) : undefined);
  const afterScore = numberOf(comparison.quality_score_after) ?? (hasReanalysis ? numberOf(reanalysis?.quality_score) : undefined);
  const beforeFindings = numberOf(comparison.findings_before) ?? (hasReanalysis ? numberOf(quality?.total_findings) : undefined);
  const afterFindings = numberOf(comparison.findings_after) ?? (hasReanalysis ? numberOf(reanalysis?.total_findings) : undefined);
  return {
    beforeScore,
    afterScore,
    beforeFindings,
    afterFindings,
    reported: Object.keys(comparison).length > 0 || hasReanalysis,
    improvementScore: beforeScore !== undefined && afterScore !== undefined ? afterScore - beforeScore : undefined,
    improvementFindings: beforeFindings !== undefined && afterFindings !== undefined ? beforeFindings - afterFindings : undefined,
  };
}

function buildStageRows(stageHistory: Record<string, unknown>[]) {
  return PIPELINE.map((stage) => {
    const matching = stageHistory.filter((entry) => stage.keys.includes(stageKey(entry.stage)));
    const current = matching[matching.length - 1];
    const status = stageStatusLabel(current?.status);
    return { ...stage, status, detail: safeText(current?.message) ?? safeText(current?.error) };
  });
}

function buildValidationReasons(validation: Record<string, unknown>, sandbox: Record<string, unknown>, errors: Array<{ agent: string; message: string }>, failed: boolean): string[] {
  const validationError = safeText(validation.error);
  const sandboxError = safeText(sandbox.error);
  return [validationError, sandboxError, ...(failed ? errors.map((error) => `${error.agent}: ${error.message}`) : [])]
    .filter((reason, index, values): reason is string => Boolean(reason) && values.indexOf(reason) === index);
}

function getToolResult(tool: string, runs: QualitySummary["tool_runs"], results: QualitySummary["tool_results"]) {
  const run = runs?.find((item) => item.tool.toLowerCase() === tool);
  const resultRecord = recordOf(results?.[tool]);
  const status = run?.status ?? safeText(resultRecord.status);
  const unavailable = run?.available === false || resultRecord.available === false || status === "skipped" || status === "not_run";
  const findingCount = typeof run?.finding_count === "number" ? run.finding_count : numberOf(resultRecord.finding_count);
  const statusText = safeText(status);
  return { status: unavailable || !statusText ? "Not analyzed" : statusDisplay(statusText), findingCount };
}

export function AnalysisReport({ result, sourceFiles, completedAt, onViewFile }: Readonly<AnalysisReportProps>) {
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);
  const report = result.final_report;
  const rawReport = recordOf(report);
  const { findings, hasFindingData, counts } = getFindingData(result, report, rawReport);
  const quality = result.quality_summary ?? report.quality_summary;
  const perFile = quality?.per_file ?? {};
  const stageHistory = useMemo(
    () => toList(result.stage_history) ?? toList(report.stage_history) ?? [],
    [result.stage_history, report.stage_history],
  );
  const attempts = toList(result.repair_attempts) ?? toList(report.repair_attempts) ?? toList(recordOf(report.workflow_summary).repair_attempts);
  const prioritized = toFindings(result.prioritized_findings) ?? toFindings(report.prioritized_findings);
  const validation = recordOf(result.validation_results ?? report.validation_results);
  const sandbox = recordOf(result.sandbox_result ?? report.sandbox_result);
  const comparison = recordOf(result.comparison ?? report.comparison);
  const reanalysisSummary = result.reanalysis_summary ?? report.reanalysis_summary;
  const agentData = getAgentData(result, report, rawReport, findings);
  const {
    securityFindings,
    resourceFindings,
    securityError,
    resourceError,
    securityReported: securityDataReported,
    resourceReported: resourceDataReported,
    securityTools,
  } = agentData;
  const {
    beforeScore: comparisonBeforeScore,
    afterScore: comparisonAfterScore,
    beforeFindings: comparisonBeforeFindings,
    afterFindings: comparisonAfterFindings,
    reported: comparisonReported,
    improvementScore,
    improvementFindings,
  } = buildComparisonData(comparison, quality, reanalysisSummary);
  const reportedValidationStatus = result.validation_status ?? report.validation_status;
  const validationStatus = reportedValidationStatus === "pending" && report.analysis_checks?.final_validation === false
    ? "not_run"
    : reportedValidationStatus;
  const qualityScore = numberOf(quality?.quality_score) ?? numberOf(quality?.quality_gate?.overall_score);
  const criticalOrHigh = (counts.critical ?? 0) + (counts.high ?? 0);
  const fileRows = buildFileRows(sourceFiles, perFile, findings);
  const selectedFile = fileRows.find((file) => file.path === selectedFilePath);
  const recommendations = buildRecommendations(report, findings);

  const stageRows = useMemo(() => buildStageRows(stageHistory), [stageHistory]);

  const validationReasons = buildValidationReasons(validation, sandbox, agentData.errorSummary, validationStatus === "failed");

  const explanation = validationExplanation(validationStatus, findings.length, validationReasons, counts);

  return (
    <article className="analysis-report" id="analysis-report" aria-label="Code validation analysis report">
      <header className="report-cover">
        <div>
          <p className="report-eyebrow">CODE VALIDATION AGENT</p>
          <h2>Analysis report</h2>
          <p className="report-project-id">{safeEvidence(result.project_id)}</p>
        </div>
        <span className={`report-status report-status--${validationClass(validationStatus)}`}>{validationLabel(validationStatus)}</span>
      </header>

      <section className="report-section report-executive" aria-labelledby="report-summary-heading">
        <div className="report-section-heading"><div><p className="report-eyebrow">01 · EXECUTIVE SUMMARY</p><h2 id="report-summary-heading">At a glance</h2></div><p>Actual results returned by this analysis run</p></div>
        <dl className="report-meta-grid">
          <Meta label="Project name" value={safeText(result.project_name) ?? safeText(rawReport.project_name)} />
          <Meta label="Project ID" value={result.project_id} />
          <Meta label="Analysis run ID" value={safeText(result.run_id) ?? safeText(result.analysis_id) ?? safeText(report.analysis_id)} />
          <Meta label="Date and time" value={formatDate(completedAt)} note={completedAt ? "Recorded when this browser received the completed run." : undefined} />
        </dl>
        <div className="report-metric-grid">
          <Metric label="Validation status" value={validationLabel(validationStatus)} tone={validationClass(validationStatus)} />
          <Metric label="Quality score" value={qualityScore} />
          <Metric label="Files analyzed" value={quality?.files_analyzed} />
          <Metric label="Total findings" value={hasFindingData ? findings.length : numberOf(recordOf(report.findings_summary).total)} />
          <Metric label="Repair attempts" value={attempts ? attempts.length : undefined} />
        </div>
        <SeveritySummary counts={counts} known={hasFindingData || Boolean(report.findings_summary?.by_severity)} />
      </section>

      <section className={`report-section report-explanation report-explanation--${validationClass(validationStatus)}`} aria-labelledby="report-explanation-heading">
        <div className="report-section-heading"><div><p className="report-eyebrow">02 · VALIDATION RESULT</p><h2 id="report-explanation-heading">{validationHeading(validationStatus)}</h2></div></div>
        <p className="report-explanation__lead">{explanation}</p>
        <div className="report-explanation__facts">
          <p><strong>Critical/high-risk findings:</strong> {hasFindingData ? `${criticalOrHigh} returned` : "Not available"}</p>
          <p><strong>Cause reported by workflow:</strong> {validationReasons.length > 0 ? validationReasons.join(" · ") : "Not available"}</p>
          <p><strong>Next step:</strong> {nextStep(validationStatus, validationReasons, recommendations, findings)}</p>
        </div>
      </section>

      <section className="report-section" aria-labelledby="report-health-heading">
        <div className="report-section-heading"><div><p className="report-eyebrow">03 · CODE HEALTH</p><h2 id="report-health-heading">Severity and quality</h2></div></div>
        <SeveritySummary counts={counts} known={hasFindingData || Boolean(report.findings_summary?.by_severity)} large />
        <div className="report-metric-grid report-metric-grid--compact">
          <Metric label="Errors reported by quality analyzer" value={quality?.errors} />
          <Metric label="Warnings reported by quality analyzer" value={quality?.warnings} />
          <Metric label="Complex functions" value={quality?.complex_functions} />
          <Metric label="Quality gate" value={safeText(quality?.quality_gate_status) ?? safeText(quality?.quality_gate?.status)} />
        </div>
        {quality?.hotspots && quality.hotspots.length > 0 && <div className="report-subsection"><h3>Complexity hotspots</h3><ul className="report-compact-list">{quality.hotspots.map((hotspot) => <li key={`${hotspot.file}-${hotspot.line}-${hotspot.function_name}`}><strong>{safeEvidence(hotspot.function_name)}</strong><span>{safeEvidence(hotspot.file ?? "Not available")}:{hotspot.line ?? "Not available"} · complexity {hotspot.complexity} · {safeEvidence(hotspot.risk_level)} risk</span></li>)}</ul></div>}
      </section>

      <section className="report-section" aria-labelledby="report-pipeline-heading">
        <div className="report-section-heading"><div><p className="report-eyebrow">04 · WORKFLOW</p><h2 id="report-pipeline-heading">Validation pipeline</h2></div><p>Stages without a backend status are marked Not reported.</p></div>
        <ol className="report-pipeline">{stageRows.map((stage, index) => <li className={`report-pipeline__stage report-pipeline__stage--${stageStatusClass(stage.status)}`} key={stage.label}><span className="report-pipeline__number">{String(index + 1).padStart(2, "0")}</span><span className="report-pipeline__name">{stage.label}</span><strong>{stage.status}</strong>{stage.detail && <small>{stage.detail}</small>}</li>)}</ol>
      </section>

      <section className="report-section" aria-labelledby="report-tools-heading">
        <div className="report-section-heading"><div><p className="report-eyebrow">05 · TOOL ANALYSIS</p><h2 id="report-tools-heading">Analyzer results</h2></div></div>
        <div className="report-table-wrap"><table className="report-table"><thead><tr><th>Tool</th><th>Status</th><th>Findings</th></tr></thead><tbody>{TOOLS.map((tool) => { const outcome = getToolResult(tool, quality?.tool_runs, quality?.tool_results); return <tr key={tool}><th scope="row">{tool[0].toUpperCase() + tool.slice(1)}</th><td><span className={`report-tool-status report-tool-status--${toolStatusClass(outcome.status)}`}>{outcome.status}</span></td><td>{display(outcome.findingCount)}</td></tr>; })}</tbody></table></div>
      </section>

      <section className="report-section" aria-labelledby="report-files-heading">
        <div className="report-section-heading"><div><p className="report-eyebrow">06 · FILE ANALYSIS</p><h2 id="report-files-heading">Files and findings</h2></div><p>{fileRows.length} file{fileRows.length === 1 ? "" : "s"} available in this report</p></div>
        <FileAnalysisTable fileRows={fileRows} hasFindingData={hasFindingData} selectedFilePath={selectedFilePath} onSelectFile={setSelectedFilePath} />
        {selectedFile && <FileDetail path={selectedFile.path} source={selectedFile.source} findings={selectedFile.findings} onViewFile={onViewFile} />}
      </section>

      <section className="report-section" aria-labelledby="report-findings-heading">
        <FindingDetailsSection findings={findings} hasFindingData={hasFindingData} sourceFiles={sourceFiles} onViewFile={onViewFile} />
      </section>

      <section className="report-section" aria-labelledby="report-priority-heading">
        <PrioritySection prioritized={prioritized} findings={findings} hasFindingData={hasFindingData} />
      </section>

      <SecuritySection error={securityError} reported={securityDataReported} findings={securityFindings} tools={securityTools} />
      <ResourceSection error={resourceError} reported={resourceDataReported} findings={resourceFindings} />

      <section className="report-section" aria-labelledby="report-repair-heading">
        <div className="report-section-heading"><div><p className="report-eyebrow">11 · REPAIR HISTORY</p><h2 id="report-repair-heading">Repair attempts</h2></div></div>
        <RepairHistorySection attempts={attempts} repairSkipped={stageRows.find((stage) => stage.label === "Repair")?.status === "Skipped"} />
      </section>

      <section className="report-section" aria-labelledby="report-comparison-heading">
        <div className="report-section-heading"><div><p className="report-eyebrow">12 · BEFORE / AFTER</p><h2 id="report-comparison-heading">Re-analysis comparison</h2></div></div>
        <ComparisonSection reported={comparisonReported} comparison={comparison} beforeFindings={comparisonBeforeFindings} afterFindings={comparisonAfterFindings} beforeScore={comparisonBeforeScore} afterScore={comparisonAfterScore} improvementFindings={improvementFindings} improvementScore={improvementScore} />
      </section>

      <AiRecommendationSection report={report} />

      <section className="report-section report-recommendation" aria-labelledby="report-recommendation-heading">
        <div className="report-section-heading"><div><p className="report-eyebrow">13 · NEXT STEPS</p><h2 id="report-recommendation-heading">Final recommendation</h2></div><span className={`report-status report-status--${validationClass(validationStatus)}`}>{recommendationStatusLabel(validationStatus)}</span></div>
        <p>{nextStep(validationStatus, validationReasons, recommendations, findings)}</p>
        {recommendations.length > 0 ? <><h3>Analyzer recommendations</h3><ol>{recommendations.map((recommendation, index) => <li key={`${index}-${recommendation}`}>{safeEvidence(recommendation)}</li>)}</ol></> : <p>No analyzer recommendations were returned.</p>}
      </section>
      <footer className="report-footnote">The report displays only data returned by the connected analysis services. Unavailable measurements are not estimated.</footer>
    </article>
  );
}

function FileAnalysisTable({ fileRows, hasFindingData, selectedFilePath, onSelectFile }: Readonly<{
  fileRows: ReportFileRow[];
  hasFindingData: boolean;
  selectedFilePath: string | null;
  onSelectFile: (path: string | null) => void;
}>) {
  if (fileRows.length === 0) return <p className="report-unavailable">File-level analysis data was not returned.</p>;
  return <div className="report-table-wrap"><table className="report-table report-file-table"><thead><tr><th>File</th><th>Findings</th><th>Quality score</th><th>Status</th><th>Details</th></tr></thead><tbody>{fileRows.map((file) => {
    const metrics = file.metrics;
    let fileStatus = safeText(metrics?.status);
    if (!fileStatus && file.findings.length > 0) fileStatus = "Findings returned";
    if (!fileStatus && hasFindingData) fileStatus = "No findings returned";
    if (!fileStatus) fileStatus = "Not available";
    const selected = selectedFilePath === file.path;
    return <tr key={file.path}><th scope="row">{safeEvidence(file.path)}</th><td>{file.findings.length}</td><td>{display(numberOf(metrics?.quality_score))}</td><td>{fileStatus}</td><td><button className="report-text-button" type="button" onClick={() => onSelectFile(selected ? null : file.path)} aria-expanded={selected}>{selected ? "Hide" : "View file"}</button></td></tr>;
  })}</tbody></table></div>;
}

function PrioritySection({ prioritized, findings, hasFindingData }: Readonly<{
  prioritized?: Finding[];
  findings: Finding[];
  hasFindingData: boolean;
}>) {
  const source = prioritized ?? findings;
  const sourceLabel = prioritized ? "Orchestrator priority data" : "Grouped by reported severity; no separate priority list was returned.";
  return <>
    <div className="report-section-heading"><div><p className="report-eyebrow">08 · FIX PRIORITY</p><h2 id="report-priority-heading">Work through findings</h2></div><p>{sourceLabel}</p></div>
    <div className="report-priority-grid">{SEVERITIES.map((severity) => <PriorityCard key={severity} severity={severity} findings={source.filter((finding) => finding.severity === severity)} known={Boolean(prioritized) || hasFindingData} />)}</div>
  </>;
}

function PriorityCard({ severity, findings, known }: Readonly<{ severity: Severity; findings: Finding[]; known: boolean }>) {
  const count = known ? findings.length : "Not available";
  const items = findings.map((finding) => <li key={finding.finding_id}>{safeEvidence(finding.file)} · {safeEvidence(finding.issue)}</li>);
  const content = findings.length === 0 && known ? <p>No issues</p> : <ul>{items}</ul>;
  return <section className={`report-priority-card report-severity--${severity}`}><h3>{severityLabel(severity)}</h3><strong>{count}</strong>{content}</section>;
}

function SecuritySection({ error, reported, findings, tools }: Readonly<{
  error?: { message: string };
  reported: boolean;
  findings: Finding[];
  tools: Record<string, unknown>[];
}>) {
  const toolText = tools.length > 0
    ? tools.map((tool) => `${safeText(tool.tool) ?? "Tool"} (${safeText(tool.status) ?? "status not reported"})`).join(", ")
    : "Not available";
  return <section className="report-section report-optional-analysis" aria-labelledby="report-security-heading">
    <div className="report-section-heading"><div><p className="report-eyebrow">09 · SECURITY</p><h2 id="report-security-heading">Security analysis</h2></div></div>
    <p className="report-availability">{availabilityMessage("Security", error, reported, findings.length)}</p>
    {reported && <><SeveritySummary counts={severityCounts(findings)} known /><p><strong>Security tools:</strong> {toolText}</p>{findings.map((finding) => <p className="report-mini-finding" key={finding.finding_id}>{safeEvidence(finding.severity)} · {safeEvidence(finding.issue)} · {safeEvidence(finding.file)}</p>)}</>}
  </section>;
}

function ResourceSection({ error, reported, findings }: Readonly<{
  error?: { message: string };
  reported: boolean;
  findings: Finding[];
}>) {
  return <section className="report-section report-optional-analysis" aria-labelledby="report-resource-heading">
    <div className="report-section-heading"><div><p className="report-eyebrow">10 · BUGS &amp; RESOURCES</p><h2 id="report-resource-heading">Bug and resource analysis</h2></div></div>
    <p className="report-availability">{availabilityMessage("Bug/resource", error, reported, findings.length)}</p>
    {reported && <div className="report-resource-grid"><Metric label="Potential bugs" value={findings.filter((finding) => finding.category === "bug").length} /><Metric label="Resource issues" value={findings.filter((finding) => finding.category === "resource").length} /><Metric label="Performance issues" value={findings.filter((finding) => /performance|slow|inefficient/i.test(`${finding.category} ${finding.subcategory ?? ""} ${finding.issue}`)).length} /><Metric label="Error-handling issues" value={findings.filter((finding) => /error.handling|exception|uncaught|failure path/i.test(`${finding.subcategory ?? ""} ${finding.issue} ${finding.description}`)).length} /></div>}
  </section>;
}

function AiRecommendationSection({ report }: Readonly<{ report: FinalReport }>) {
  const status = report.ai_recommendations_status;
  if (!status || status.status === "disabled") return null;
  const content = status.status === "completed"
    ? <AiRecommendationContent report={report} />
    : <p className="report-availability">{status.message ?? "The AI report/recommendation stage did not return results."}</p>;
  return <section className="report-section" aria-labelledby="report-ai-heading">
    <div className="report-section-heading"><div><p className="report-eyebrow">AI REVIEW</p><h2 id="report-ai-heading">Report and recommendations</h2></div><span>{status.status.toUpperCase()}</span></div>
    {content}
  </section>;
}

function AiRecommendationContent({ report }: Readonly<{ report: FinalReport }>) {
  const issues = report.code_report?.issues ?? [];
  const fixes = report.recommendation_report?.fixes ?? [];
  const suggestions = report.recommendation_report?.suggestions ?? [];
  return <>
    <p className="report-availability">Independent Gemini review of {report.code_report?.scanned_files ?? 0} submitted files. Suggested changes are review-only and have not been applied.</p>
    <h3>Additional issues</h3>
    {issues.length > 0 ? <ol className="report-ai-list">{issues.map((issue, index) => <li key={`${issue.file_path}-${issue.line_number}-${index}`}><strong>{safeEvidence(issue.issue_type)}</strong> · {safeEvidence(issue.file_path)}:{issue.line_number}<p>{safeEvidence(issue.description)}</p></li>)}</ol> : <p className="report-empty">No additional issues were returned.</p>}
    <h3>Proposed fixes</h3>
    {fixes.length > 0 ? <ol className="report-ai-list">{fixes.map((fix, index) => <li key={`${fix.file_path}-${fix.line_number}-${index}`}><strong>{safeEvidence(fix.file_path)}:{fix.line_number}</strong><p>{safeEvidence(fix.explanation)}</p><div className="report-ai-code"><span>Original</span><pre><code>{safeEvidence(fix.original_code)}</code></pre></div><div className="report-ai-code"><span>Suggested</span><pre><code>{safeEvidence(fix.suggested_code)}</code></pre></div></li>)}</ol> : <p className="report-empty">No code fixes were returned.</p>}
    <h3>Project suggestions</h3>
    {suggestions.length > 0 ? <ul className="report-ai-list">{suggestions.map((suggestion, index) => <li key={`${suggestion.category}-${index}`}><strong>{safeEvidence(suggestion.category)}:</strong> {safeEvidence(suggestion.suggestion)}<p>{safeEvidence(suggestion.benefit)}</p></li>)}</ul> : <p className="report-empty">No project-level suggestions were returned.</p>}
  </>;
}

function FindingDetailsSection({ findings, hasFindingData, sourceFiles, onViewFile }: Readonly<{
  findings: Finding[];
  hasFindingData: boolean;
  sourceFiles: ProjectFile[];
  onViewFile: (path: string) => void;
}>) {
  let content;
  if (!hasFindingData) {
    content = <p className="report-unavailable">Finding details are not available for this run.</p>;
  } else if (findings.length === 0) {
    content = <p className="report-empty">No findings were returned by the available analyzers.</p>;
  } else {
    content = <div className="report-finding-list">{[...findings].sort((first, second) => severityRank(first.severity) - severityRank(second.severity) || first.file.localeCompare(second.file)).map((finding) => <FindingDetail key={finding.finding_id} finding={finding} source={sourceFiles.find((file) => file.path === finding.file)} onViewFile={onViewFile} />)}</div>;
  }
  return <>
    <div className="report-section-heading"><div><p className="report-eyebrow">07 · FINDING DETAILS</p><h2 id="report-findings-heading">What needs attention</h2></div><p>{findingSummary(hasFindingData, findings)}</p></div>
    {content}
  </>;
}

function RepairHistorySection({ attempts, repairSkipped }: Readonly<{ attempts?: Record<string, unknown>[]; repairSkipped: boolean }>) {
  if (attempts === undefined) return <p className="report-unavailable">Repair attempt history was not returned by the workflow.</p>;
  if (attempts.length === 0) return <p className="report-empty">{repairSkipped ? "No repair was required." : "No repair attempts were returned."}</p>;
  return <ol className="report-attempt-list">{attempts.map((attempt, index) => <li key={`${safeText(attempt.attempt_id) ?? "attempt"}-${index}`}><div className="report-attempt-heading"><h3>Attempt {safeText(attempt.iteration) ?? index + 1}</h3><span>{safeText(attempt.outcome) ?? safeText(attempt.status) ?? "Status not available"}</span></div><dl><Meta label="Mode" value={safeText(attempt.mode)} /><Meta label="Files changed" value={Array.isArray(attempt.changed_files) ? attempt.changed_files.length : undefined} /><Meta label="Findings detected" value={numberOf(attempt.findings_detected)} /><Meta label="Validation" value={safeText(recordOf(attempt.validation).status) ?? safeText(attempt.validation_status)} /></dl>{safeText(attempt.error) && <p className="report-availability">{safeText(attempt.error)}</p>}</li>)}</ol>;
}

function ComparisonSection({ reported, comparison, beforeFindings, afterFindings, beforeScore, afterScore, improvementFindings, improvementScore }: Readonly<{
  reported: boolean;
  comparison: Record<string, unknown>;
  beforeFindings?: number;
  afterFindings?: number;
  beforeScore?: number;
  afterScore?: number;
  improvementFindings?: number;
  improvementScore?: number;
}>) {
  const hasComparisonValues = beforeFindings !== undefined || afterFindings !== undefined || beforeScore !== undefined || afterScore !== undefined;
  if (!reported || !hasComparisonValues) return <p className="report-unavailable">Before/after comparison data was not returned for this run.</p>;
  let findingSign = "";
  if (improvementFindings !== undefined && improvementFindings > 0) findingSign = "-";
  if (improvementFindings !== undefined && improvementFindings < 0) findingSign = "+";
  return <>
    <div className="report-comparison-grid"><ComparisonColumn title="Before repair" qualityScore={beforeScore} findingCount={beforeFindings} severity={recordOf(comparison.findings_by_severity_before)} /><ComparisonColumn title="After repair" qualityScore={afterScore} findingCount={afterFindings} severity={recordOf(comparison.findings_by_severity_after)} /></div>
    {improvementScore !== undefined && <p className="report-improvement">Quality score change: {improvementScore > 0 ? "+" : ""}{improvementScore}</p>}
    {improvementFindings !== undefined && <p className="report-improvement">Finding reduction: {findingSign}{Math.abs(improvementFindings)}</p>}
  </>;
}

function Meta({ label, value, note }: Readonly<{ label: string; value?: string | number; note?: string }>) {
  return <div className="report-meta"><dt>{label}</dt><dd>{display(value)}</dd>{note && <small>{note}</small>}</div>;
}

function Metric({ label, value, tone }: Readonly<{ label: string; value?: string | number; tone?: string }>) {
  const className = ["report-metric", tone ? `report-metric--${tone}` : ""].filter(Boolean).join(" ");
  return <div className={className}><span>{label}</span><strong>{display(value)}</strong></div>;
}

function SeveritySummary({ counts, known, large = false }: Readonly<{ counts: Record<Severity, number | undefined>; known: boolean; large?: boolean }>) {
  return <div className={`report-severity-grid${large ? " report-severity-grid--large" : ""}`}>{SEVERITIES.map((severity) => <div className={`report-severity-card report-severity--${severity}`} key={severity}><span>{severityLabel(severity)}</span><strong>{known && counts[severity] !== undefined ? counts[severity] : "Not available"}</strong></div>)}</div>;
}

function FindingDetail({ finding, source, onViewFile }: Readonly<{ finding: Finding; source?: ProjectFile; onViewFile: (path: string) => void }>) {
  const code = findingCode(finding);
  const displayTitle = textOf(finding.description) ?? textOf(finding.issue) ?? "Finding details not available";
  return <details className={`report-finding report-finding--${finding.severity}`} open>
    <summary><span className={`report-severity-pill report-severity-pill--${finding.severity}`}>{finding.severity.toUpperCase()}</span><span>{safeEvidence(finding.tool ?? finding.detected_by_tools?.join(", ") ?? "Tool not available")}</span><code>{safeEvidence(code)}</code><strong>{safeEvidence(displayTitle)}</strong></summary>
    <div className="report-finding__body">
      <dl className="report-finding__meta"><Meta label="Rule / code" value={code} /><Meta label="File" value={safeEvidence(finding.file)} /><Meta label="Line" value={finding.line_number === null ? undefined : String(finding.line_number)} /><Meta label="Finding status" value={safeText(finding.status)} /></dl>
      <p><strong>Why this matters:</strong> {textOf(finding.description) ? safeEvidence(finding.description) : "The analyzer did not provide an explanation."}</p>
      <p><strong>Suggested action:</strong> {textOf(finding.recommendation) ? safeEvidence(finding.recommendation) : "Not available"}</p>
      <p><strong>Detected by:</strong> {safeEvidence(finding.tool ?? finding.detected_by_tools?.join(", ") ?? "Not available")}</p>
      {finding.evidence && <p><strong>Evidence:</strong> {safeEvidence(finding.evidence)}</p>}
      {source ? <><SourceExcerpt source={source} line={finding.line_number} /><button className="report-text-button report-view-file" type="button" onClick={() => onViewFile(finding.file)}>View File</button></> : <p className="report-unavailable">Source code was not available for this file. Location: {safeEvidence(finding.file)}{finding.line_number === null ? "" : ` · line ${finding.line_number}`}</p>}
    </div>
  </details>;
}

function FileDetail({ path, source, findings, onViewFile }: Readonly<{ path: string; source?: ProjectFile; findings: Finding[]; onViewFile: (path: string) => void }>) {
  return <section className="report-file-detail"><div className="report-section-heading"><div><p className="report-eyebrow">SELECTED FILE</p><h3>{safeEvidence(path)}</h3></div><button className="report-text-button report-view-file" type="button" onClick={() => onViewFile(path)}>View File</button></div>
    {findings.length > 0 ? <div className="report-finding-list">{findings.map((finding) => <FindingDetail key={finding.finding_id} finding={finding} source={source} onViewFile={onViewFile} />)}</div> : <p className="report-empty">No findings were returned for this file.</p>}
    {source ? <details className="report-source-full"><summary>Show full source file</summary><SourceExcerpt source={source} /></details> : <p className="report-unavailable">Source content is not available in this browser session.</p>}
  </section>;
}

function SourceExcerpt({ source, line }: Readonly<{ source: ProjectFile; line?: number | null }>) {
  const lines = source.content.split(/\r?\n/);
  const start = line === undefined || line === null ? 0 : Math.max(0, line - 3);
  const end = line === undefined || line === null ? lines.length : Math.min(lines.length, line + 2);
  return <div className="report-code-block"><p>{safeEvidence(source.path)}{line ? ` · around line ${line}` : ""}</p><pre>{lines.slice(start, end).map((content, index) => { const lineNumber = start + index + 1; return <span className={lineNumber === line ? "report-code-line report-code-line--highlight" : "report-code-line"} key={lineNumber}><b>{lineNumber}</b><code>{content ? safeEvidence(content) : " "}</code></span>; })}</pre></div>;
}

function ComparisonColumn({ title, qualityScore, findingCount, severity }: Readonly<{ title: string; qualityScore?: number; findingCount?: number; severity: Record<string, unknown> }>) {
  return <section className="report-comparison-column"><h3>{title}</h3><Metric label="Quality score" value={qualityScore} /><Metric label="Findings" value={findingCount} />{SEVERITIES.map((level) => <p key={level}><span>{severityLabel(level)}</span><strong>{numberOf(severity[level]) ?? "Not available"}</strong></p>)}</section>;
}

function nextStep(status: string, reasons: string[], recommendations: string[], findings: Finding[]): string {
  if (status === "not_run") return "Review the available analysis results; final validation was not run.";
  if (status === "failed" && reasons.length > 0) return "Resolve the reported workflow or validation issue, then run validation again.";
  if (recommendations.length > 0) return safeEvidence(recommendations[0]);
  if (findings.length > 0) return "Review the finding details and suggested actions, then rerun validation after changes.";
  if (status === "passed") return "Review the returned evidence and proceed with your normal code review.";
  return "Wait for a final workflow result, or check the reported service availability.";
}

function statusDisplay(status: string): string {
  const normalized = status.toLowerCase().replace(/[_-]/g, " ");
  return normalized.replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function severityRank(severity: Severity): number {
  return SEVERITIES.indexOf(severity);
}

function severityLabel(severity: Severity): string {
  return severity[0].toUpperCase() + severity.slice(1);
}