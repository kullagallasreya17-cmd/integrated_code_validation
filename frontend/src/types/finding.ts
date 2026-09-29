export type Severity = "low" | "medium" | "high" | "critical" | "info";
export type FindingStatus = "Open" | "In repair" | "Fixed (validated)" | "Needs human review" | "False positive" | "Won't fix" | "open" | "repaired" | "ignored";

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
  status: FindingStatus;
  tool?: string;
  detected_by_tools?: string[];
  subcategory?: string;
  requires_human_review?: boolean;
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
  workflow_summary?: WorkflowSummary;
  workflow_trace?: string[];
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
  quality_score?: number;
  quality_gate_status?: string;
  quality_gate?: {
    status: string;
    overall_score: number;
    thresholds: Record<string, number>;
  };
  maintainability?: Record<string, unknown>;
  tool_runs?: Array<{ tool: string; agent?: string; status: string; finding_count: number; duration_ms?: number; exit_code?: number | null; error?: string; raw_output?: string; available?: boolean }>;
  tool_results?: Record<string, { status?: string; duration_ms?: number; exit_code?: number | null; error?: string; raw_output?: string; available?: boolean; agent?: string; finding_count?: number }>;
  hotspots?: Array<{ function_name: string; file: string | null; line: number | null; complexity: number; risk_level: string }>;
  per_file?: Record<string, { errors: number; warnings: number; complexity: string; issues: number }>;
}

export interface WorkflowSummary {
  workflow_status: string;
  total_findings: number;
  findings_by_severity: Record<string, number>;
  quality_score: number;
  quality_gate: string;
  repair_attempts: Array<Record<string, unknown>>;
  validation_result: Record<string, unknown>;
  agent_failures: Array<{ agent: string; error: string }>;
  workflow_duration_seconds?: number;
}

export interface WorkflowRunResponse {
  run_id?: string;
  analysis_configuration?: {
    readonly sandbox_timeout_seconds: number;
    readonly memory_limit_mb: number;
    readonly cpu_limit: number;
    readonly network_policy: "restricted" | "off";
    readonly llm_provider: string;
    readonly model_name: string;
  };
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
