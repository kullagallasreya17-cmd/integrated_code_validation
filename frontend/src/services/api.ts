import type { ProgressEvent, ProjectFile, QualityTool, WorkflowRunResponse } from "../types/finding";

// In production this points at the API gateway, not the orchestrator
// directly, so the frontend never needs to know about individual
// backend services.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface StartAnalysisPayload {
  project_id: string;
  files: ProjectFile[];
  project_context?: Record<string, unknown>;
  tools?: QualityTool[];
}

interface StartAnalysisResponse {
  project_id: string;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }

  return res.json() as Promise<T>;
}

export const api = {
  /** Starts a run, then consumes its server-sent progress and result events. */
  async startAnalysis(
    payload: StartAnalysisPayload,
    onProgress: (progress: ProgressEvent) => void,
  ): Promise<WorkflowRunResponse> {
    const started = await request<StartAnalysisResponse>("/analysis/run", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    return new Promise((resolve, reject) => {
      const source = new EventSource(`${API_BASE_URL}/analysis/stream/${started.project_id}`);
      let settled = false;

      const finish = (callback: () => void) => {
        if (settled) return;
        settled = true;
        source.close();
        callback();
      };

      source.addEventListener("progress", (event) => {
        onProgress(JSON.parse((event as MessageEvent).data) as ProgressEvent);
      });
      source.addEventListener("complete", (event) => {
        const data = JSON.parse((event as MessageEvent).data) as { result: WorkflowRunResponse };
        finish(() => resolve(data.result));
      });
      source.addEventListener("failed", (event) => {
        const data = (event as MessageEvent).data;
        finish(() => reject(new Error(data ? JSON.parse(data).message : "Analysis stream failed")));
      });
      source.onerror = () => {
        if (!settled) finish(() => reject(new Error("Backend unreachable or analysis stream disconnected")));
      };
    });
  },

  health(): Promise<{ status: string; service: string }> {
    return request("/health");
  },

  status(projectId: string): Promise<Record<string, unknown>> {
    return request(`/analysis/status/${projectId}`);
  },

  agentCard(): Promise<Record<string, unknown>> {
    return request(`${import.meta.env.VITE_ORCHESTRATOR_URL ?? "http://localhost:8001"}/.well-known/agent-card.json`);
  },
};
