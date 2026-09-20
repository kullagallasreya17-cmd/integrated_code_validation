export type Severity = "low" | "medium" | "high" | "critical" | "info";

export interface Finding {
  finding_id: string;
  category: "security" | "code_quality" | "resource" | "bug" | "maintainability";
  severity: Severity;
  file: string;
  line_number: number | null;
  issue: string;
  description: string;
  evidence?: string;
  recommendation?: string;
  status: "open" | "repaired" | "ignored";
  tool?: string;
  subcategory?: string;
}

export interface ProjectFile {
  path: string;
  content: string;
}

export type ValidationStatus = "pending" | "passed" | "failed" | "unknown";

export interface FinalReport {
  project_id: string;
  validation_status: ValidationStatus;
  retry_count: number;
  max_retries: number;
  findings_summary: {
    total: number;
    by_severity: Record<Severity, number>;
  };
  validation_results: Record<string, unknown>;
  agent_errors?: Array<{ agent: string; error: string }>;
  repair_attempts?: Array<Record<string, unknown>>;
  stage_history?: Array<Record<string, unknown>>;
  sandbox_result?: Record<string, unknown>;
  final_code?: Record<string, string>;
  quality_summary?: QualitySummary;
  reanalysis_summary?: QualitySummary;
  comparison?: {
    findings_before: number;
    findings_after: number;
    resolved_issues: string[];
    remaining_issues: string[];
    changed_files: string[];
    improved: boolean;
  };
}

export interface QualitySummary {
  files_analyzed: number;
  total_findings: number;
  errors: number;
  warnings: number;
  info: number;
  complex_functions: number;
  by_tool: Record<string, number>;
  by_severity: Record<string, number>;
}

export interface WorkflowRunResponse {
  project_id: string;
  validation_status: ValidationStatus;
  retry_count: number;
  findings: Finding[];
  final_report: FinalReport;
}

export type QualityTool = "ruff" | "pylint" | "radon";
export type SecurityTool = "semgrep" | "bandit" | "gitleaks";

export interface RunHistoryEntry {
  project_id: string;
  timestamp: string;
  validation_status: ValidationStatus;
  result: WorkflowRunResponse;
  originalFiles: ProjectFile[];
}

export interface ProgressEvent {
  step: string;
  message: string;
}
