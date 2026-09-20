import type { FinalReport } from "../types/finding";

interface ValidationResultProps {
  report: FinalReport;
}

export function ValidationResult({ report }: ValidationResultProps) {
  const passed = report.validation_status === "passed";

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
    </div>
  );
}
