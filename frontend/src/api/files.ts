import { apiClient, mocksEnabled } from "./client";
import type { ProjectFile } from "./types";

export interface ProjectFilesResponse {
  readonly project_id: string;
  readonly files: ProjectFile[];
}

const mockProjectFiles = new Map<string, ProjectFile[]>();
window.addEventListener("coding-validation:clear-user-data", () => mockProjectFiles.clear());

function normalizeSeparators(path: string): string {
  return [...path].map((character) => character === "\\" ? "/" : character).join("");
}

export function setMockProjectFiles(projectId: string, files: ProjectFile[]): void {
  mockProjectFiles.set(projectId, [...files]);
}

export function deleteMockProjectFiles(projectId: string): void {
  mockProjectFiles.delete(projectId);
}

export function validatePythonPath(value: string): string {
  const path = normalizeSeparators(value.trim());
  if (!path || path.startsWith("/") || /^[a-z]:/i.test(path)) throw new Error("Use a relative Python file path.");
  if (path.split("/").some((segment) => segment === ".." || segment === "")) throw new Error("Path segments cannot be empty or contain '..'.");
  if (!path.toLowerCase().endsWith(".py")) throw new Error("Only Python source files (.py) are supported.");
  return path;
}

export async function getProjectFiles(projectId: string, signal?: AbortSignal): Promise<ProjectFilesResponse> {
  if (mocksEnabled()) {
    const files = mockProjectFiles.get(projectId);
    if (!files) throw new Error("Project files were not found in mock data.");
    return { project_id: projectId, files };
  }
  return apiClient.get<ProjectFilesResponse>(`/api/files?project_id=${encodeURIComponent(projectId)}`, signal);
}

export async function saveProjectFiles(projectId: string, files: ProjectFile[], signal?: AbortSignal): Promise<ProjectFilesResponse> {
  const safeFiles = files.map((file) => ({ ...file, path: validatePythonPath(file.path) }));
  if (mocksEnabled()) {
    mockProjectFiles.set(projectId, safeFiles);
    return { project_id: projectId, files: safeFiles };
  }
  return apiClient.post<ProjectFilesResponse>("/api/files", { project_id: projectId, files: safeFiles }, signal);
}

export async function saveProjectFile(projectId: string, file: ProjectFile, signal?: AbortSignal): Promise<void> {
  const path = validatePythonPath(file.path);
  const existing = await getProjectFiles(projectId, signal);
  await saveProjectFiles(projectId, [...existing.files.filter((item) => item.path !== path), { path, content: file.content }], signal);
}

export async function renameProjectFile(projectId: string, oldPath: string, newPath: string, signal?: AbortSignal): Promise<void> {
  const source = validatePythonPath(oldPath);
  const target = validatePythonPath(newPath);
  const files = (await getProjectFiles(projectId, signal)).files;
  if (!files.some((item) => item.path === source)) throw new Error("File was not found.");
  if (files.some((item) => item.path === target)) throw new Error("A file with that path already exists.");
  await saveProjectFiles(projectId, files.map((item) => item.path === source ? { ...item, path: target } : item), signal);
}

export async function deleteProjectFile(projectId: string, path: string, signal?: AbortSignal): Promise<void> {
  const safePath = validatePythonPath(path);
  const files = (await getProjectFiles(projectId, signal)).files;
  await saveProjectFiles(projectId, files.filter((file) => file.path !== safePath), signal);
}
