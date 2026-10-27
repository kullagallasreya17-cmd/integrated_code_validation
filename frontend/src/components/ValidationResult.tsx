import type { FinalReport, WorkflowRunResponse } from "../types/finding";

interface ValidationResultProps {
  report: FinalReport;
  sandboxConfiguration: WorkflowRunResponse["analysis_configuration"];
}

function settingText(...values: unknown[]): string {
  const value = values.find((candidate) => typeof candidate === "string" || typeof candidate === "number" || typeof candidate === "boolean");
  return value === undefined ? "Not reported" : String(value);
}

export function ValidationResult({ report, sandboxConfiguration }: Readonly<ValidationResultProps>) {
  const passed = report.validation_status === "passed";
  const validationEvidence = report.validation_results;
  const validatorStatus = typeof validationEvidence.validator_status === "string"
    ? validationEvidence.validator_status.replace(/_/g, " ")
    : typeof validationEvidence.validator_passed === "boolean"
      ? validationEvidence.validator_passed ? "passed" : "failed"
      : "not reported";
  const sandboxStatus = report.sandbox_result?.passed === true
    ? "passed"
    : typeof report.sandbox_result?.status === "string"
      ? report.sandbox_result.status.replace(/_/g, " ")
      : report.sandbox_result?.executed === false ? "not executed" : "not reported";
  const statusLabel = report.validation_status === "needs_review"
    ? "Validation completed — review findings"
    : report.validation_status === "error"
      ? "Validation could not complete"
      : report.validation_status === "blocked"
        ? "Validation blocked"
        : report.validation_status === "not_run"
          ? "Validation was not run"
          : report.validation_status === "pending"
            ? "Validation is still in progress"
            : report.validation_status === "inconclusive"
              ? "Validation result is inconclusive"
            : passed ? "Validation passed" : "Validation failed";
  const validationError = typeof validationEvidence.error === "string"
    ? validationEvidence.error
    : typeof report.sandbox_result?.error === "string" ? report.sandbox_result.error : undefined;
  const sandboxEvidence = validationEvidence.sandbox_settings ?? report.sandbox_result?.settings ?? report.sandbox_result?.configuration;
  const comparison = report.comparison;
  const finalFindingCount = comparison?.status === "complete"
    ? comparison.findings_after
    : report.findings_summary.total;
  const severitySummary = comparison?.status === "complete" && comparison.findings_by_severity_after
    ? comparison.findings_by_severity_after
    : report.findings_summary.by_severity;
  const effectiveSettings = sandboxEvidence !== null && typeof sandboxEvidence === "object" ? sandboxEvidence as Record<string, unknown> : undefined;
  const displayedSettings: Record<string, unknown> = effectiveSettings ?? sandboxConfiguration ?? {};
  const hasSettings = Object.keys(displayedSettings).length > 0;

  return (
    <div className={`validation-result validation-result--${passed ? "pass" : "fail"}`}>
      <h3>{statusLabel}</h3>
      {validationError && <p role="alert">{validationError}</p>}
      <ul className="validation-result__breakdown">
        <li>Static validator: {validatorStatus}</li>
        <li>Sandbox execution: {sandboxStatus}</li>
        <li>Quality gate: {comparison?.status === "complete"
          ? report.reanalysis_summary?.quality_gate_status ?? report.reanalysis_summary?.quality_gate?.status ?? "not reported"
          : report.quality_summary?.quality_gate_status ?? report.quality_summary?.quality_gate?.status ?? "not reported"}</li>
      </ul>
      <p>
        Retries used: {report.retry_count} / {report.max_retries}
      </p>
      <p>Remaining findings: {finalFindingCount ?? "Not reported"}</p>
      <ul className="validation-result__breakdown">
        {Object.entries(severitySummary).map(([severity, count]) => (
          <li key={severity}>
            {severity}: {count}
          </li>
        ))}
      </ul>
      <details className="sandbox-settings-evidence">
        <summary>{effectiveSettings ? "Effective sandbox settings" : "Sandbox options sent for this run"}</summary>
        {hasSettings ? <dl>
          <dt>Timeout</dt><dd>{settingText(displayedSettings.sandbox_timeout_seconds, displayedSettings.timeout_seconds)} seconds</dd>
          <dt>Memory</dt><dd>{settingText(displayedSettings.memory_limit_mb, displayedSettings.memory_limit)} MB</dd>
          <dt>CPU</dt><dd>{settingText(displayedSettings.cpu_limit)}</dd>
          <dt>Network</dt><dd>{settingText(displayedSettings.network_policy)}</dd>
        </dl> : <p>Sandbox settings were not returned by the workflow.</p>}
        {!effectiveSettings && sandboxConfiguration && <p>The gateway has not confirmed that these requested options were applied.</p>}
      </details>
    </div>
  );
}
