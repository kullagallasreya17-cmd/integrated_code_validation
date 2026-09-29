import type { ProgressEvent, ProjectFile, QualityTool, WorkflowRunResponse } from "../types/finding";
import { apiBaseUrl, apiClient, mocksEnabled } from "../api/client";
import type { StartAnalysisResponse } from "../api/types";

// In production this points at the API gateway, not individual agent services.
export interface StartAnalysisPayload {
  project_id: string;
  files: ProjectFile[];
  project_context?: Record<string, unknown>;
  tools?: QualityTool[];
}

interface StreamCompleteEvent {
  readonly result?: WorkflowRunResponse;
}

function parseEvent<T>(event: MessageEvent<string>): T {
  return JSON.parse(event.data) as T;
}

export const api = {
  async startAnalysis(payload: StartAnalysisPayload, onProgress: (progress: ProgressEvent) => void): Promise<WorkflowRunResponse> {
    if (mocksEnabled()) return runMockAnalysis(payload, onProgress);
    const started = await apiClient.post<StartAnalysisResponse>("/analysis/run", payload);
    const projectId = started.project_id || payload.project_id;

    return new Promise((resolve, reject) => {
      const source = new EventSource(`${apiBaseUrl()}/analysis/stream/${encodeURIComponent(projectId)}`);
      let settled = false;
      const finish = (callback: () => void) => {
        if (settled) return;
        settled = true;
        source.close();
        callback();
      };

      source.addEventListener("progress", (event) => {
        try {
          onProgress(parseEvent<ProgressEvent>(event as MessageEvent<string>));
        } catch {
          onProgress({ step: "unknown", message: "Received a progress update." });
        }
      });
      source.addEventListener("complete", (event) => {
        try {
          const data = parseEvent<StreamCompleteEvent>(event as MessageEvent<string>);
          if (!data.result) throw new Error("Missing workflow result");
          finish(() => resolve(data.result as WorkflowRunResponse));
        } catch {
          finish(() => reject(new Error("The workflow completed without a readable result.")));
        }
      });
      source.addEventListener("failed", () => finish(() => reject(new Error("The analysis workflow failed. Review the run status and retry if appropriate."))));
      source.onerror = () => {
        if (source.readyState === EventSource.CLOSED) finish(() => reject(new Error("The analysis event stream closed before a final result was received.")));
      };
    });
  },
  health(): Promise<{ status: string; service: string }> {
    return apiClient.get("/health");
  },
  status(projectId: string): Promise<Record<string, unknown>> {
    return apiClient.get(`/analysis/status/${encodeURIComponent(projectId)}`);
  },
  async agentCard(): Promise<Record<string, unknown>> {
    const url = `${import.meta.env.VITE_ORCHESTRATOR_URL ?? "http://localhost:8001"}/.well-known/agent-card.json`;
    try {
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("Agent information is unavailable.");
      return await response.json() as Record<string, unknown>;
    } catch {
      throw new Error("Unable to load agent information.");
    }
  },
};

async function runMockAnalysis(payload: StartAnalysisPayload, onProgress: (progress: ProgressEvent) => void): Promise<WorkflowRunResponse> {
  const steps = ["understand", "analyze", "aggregate", "repair", "validate", "finalize"];
  for (const step of steps) {
    onProgress({ step, message: `Mock workflow: ${step}` });
    await new Promise<void>((resolve) => window.setTimeout(resolve, 80));
  }
  const firstFile = payload.files[0];
  const finding = firstFile ? {
    finding_id: "mock-finding-001",
    category: "code_quality" as const,
    severity: "medium" as const,
    file: firstFile.path,
    line_number: 1,
    issue: "COMPLEXITY_B: example function has branching",
    description: "Mock finding used to exercise the evidence and status views.",
    evidence: "Mock evidence only; no analyzer was executed.",
    recommendation: "Review the branching structure.",
    status: "Open" as const,
    tool: "radon",
  } : undefined;
  const findings = finding ? [finding] : [];
  const repaired = firstFile ? { ...firstFile, content: `# Mock validated repair candidate\n${firstFile.content}` } : undefined;
  const configuredSandbox = payload.project_context ?? {};
  const toolNames = ["Semgrep", "Bandit", "Gitleaks", "Ruff", "Pylint", "Radon", "Pytest", "Coverage"];
  const toolResults = Object.fromEntries(toolNames.map((tool) => {
    const qualityTool = ["Ruff", "Pylint", "Radon"].includes(tool);
    return [tool.toLowerCase(), { agent: qualityTool ? "Code Quality Agent" : "Security/Validation Agent", status: qualityTool ? "completed" : "skipped", available: qualityTool, finding_count: qualityTool && tool === "Radon" ? findings.length : 0, duration_ms: qualityTool ? 18 : undefined, exit_code: qualityTool ? 0 : null, raw_output: qualityTool ? `Mock ${tool} output; no external tool executed.` : undefined }];
  }));
  const qualitySummary = {
    files_analyzed: payload.files.length, total_findings: findings.length, errors: 0, warnings: findings.length, info: 0,
    complex_functions: 1, by_tool: { ruff: 0, pylint: 0, radon: findings.length }, by_severity: { critical: 0, high: 0, medium: findings.length, low: 0, info: 0 },
    quality_score: 92, quality_gate_status: "PASS", maintainability: { maintainability_index: 84 },
    tool_runs: toolNames.map((tool) => ({ tool: tool.toLowerCase(), agent: toolResults[tool.toLowerCase()].agent, status: toolResults[tool.toLowerCase()].status, finding_count: toolResults[tool.toLowerCase()].finding_count, duration_ms: toolResults[tool.toLowerCase()].duration_ms, exit_code: toolResults[tool.toLowerCase()].exit_code, available: toolResults[tool.toLowerCase()].available, raw_output: toolResults[tool.toLowerCase()].raw_output })),
    tool_results: toolResults,
    hotspots: [{ function_name: "example", file: firstFile?.path ?? null, line: 1, complexity: 10, risk_level: "Low" }],
    per_file: Object.fromEntries(payload.files.map((file) => [file.path, { errors: 0, warnings: findings.length, complexity: "Low", issues: findings.length }])),
  };
  const runId = `mock-run-${crypto.randomUUID()}`;
  const report = {
    project_id: payload.project_id, validation_status: "passed" as const, retry_count: 1, max_retries: 3,
    findings_summary: { total: findings.length, by_severity: { critical: 0, high: 0, medium: findings.length, low: 0, info: 0 } },
    validation_results: { validation_id: `mock-validation-${crypto.randomUUID()}`, status: "PASS", sandbox_settings: configuredSandbox },
    repair_attempts: [{ attempt_id: `mock-repair-${crypto.randomUUID()}`, iteration: 1, status: "accepted", validation: { status: "PASS" } }],
    stage_history: steps.map((stage) => ({ stage, status: "completed" })), workflow_trace: steps,
    sandbox_result: { executed: true, duration_ms: 24, peak_memory_mb: 18, cpu_percent: 7, settings: configuredSandbox },
    final_code: repaired ? { [repaired.path]: repaired.content } : {},
    quality_summary: qualitySummary,
    workflow_summary: { workflow_status: "SUCCESS", total_findings: findings.length, findings_by_severity: { critical: 0, high: 0, medium: findings.length, low: 0, info: 0 }, quality_score: 92, quality_gate: "PASS", repair_attempts: [], validation_result: { status: "PASS" }, agent_failures: [], workflow_duration_seconds: 0.5 },
  };
  return { run_id: runId, project_id: payload.project_id, validation_status: "passed", retry_count: 1, findings, final_report: report };
}
