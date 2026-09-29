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
  const sandboxEvidence = validationEvidence.sandbox_settings ?? report.sandbox_result?.settings ?? report.sandbox_result?.configuration;
  const effectiveSettings = sandboxEvidence !== null && typeof sandboxEvidence === "object" ? sandboxEvidence as Record<string, unknown> : undefined;
  const displayedSettings: Record<string, unknown> = effectiveSettings ?? sandboxConfiguration ?? {};
  const hasSettings = Object.keys(displayedSettings).length > 0;

  return (
    <div className={`validation-result validation-result--${passed ? "pass" : "fail"}`}>
      <h3>{passed ? "Validation passed" : "Validation failed"}</h3>
      <p>
        Retries used: {report.retry_count} / {report.max_retries}
      </p>
      <p>Total findings: {report.findings_summary.total}</p>
      <ul className="validation-result__breakdown">
        {Object.entries(report.findings_summary.by_severity).map(([severity, count]) => (
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
