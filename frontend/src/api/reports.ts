import { apiClient, mocksEnabled } from "./client";
import type { Report } from "./types";

export async function getReport(projectId: string, signal?: AbortSignal): Promise<Report> {
  if (mocksEnabled()) return { project_id: projectId, status: "completed", report: { findings: [], recommendations: [] } };
  return apiClient.get<Report>(`/results/${encodeURIComponent(projectId)}`, signal);
}
