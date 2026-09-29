import type { AuthSession } from "./types";

const API_BASE_URL = (import.meta.env.VITE_API_URL ?? import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const TOKEN_KEY = "coding-validation-token";

export class ApiError extends Error {
  readonly status: number;
  readonly safeDetails?: string;

  constructor(message: string, status: number, safeDetails?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.safeDetails = safeDetails;
  }
}

export function mocksEnabled(): boolean {
  return import.meta.env.VITE_USE_MOCKS === "true";
}

export function saveSession(session: AuthSession, _remember: boolean): void {
  clearSession();
  const storage = window.sessionStorage;
  storage.setItem(TOKEN_KEY, session.access_token);
  storage.setItem(`${TOKEN_KEY}-user`, JSON.stringify(session.user));
}

export function readSession(): AuthSession | null {
  const serialized = window.sessionStorage.getItem(`${TOKEN_KEY}-user`);
  const accessToken = window.sessionStorage.getItem(TOKEN_KEY);
  if (!serialized || !accessToken) return null;
  try {
    return { access_token: accessToken, token_type: "Bearer", user: JSON.parse(serialized) as AuthSession["user"] };
  } catch {
    clearSession();
    return null;
  }
}

export function clearSession(): void {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(`${TOKEN_KEY}-user`);
  window.sessionStorage.removeItem(TOKEN_KEY);
  window.sessionStorage.removeItem(`${TOKEN_KEY}-user`);
}

function safeError(status: number): ApiError {
  const messages: Record<number, string> = {
    400: "The request could not be understood. Check the submitted information.",
    401: "Your session is missing or has expired. Please sign in again.",
    403: "You do not have permission to perform this action.",
    404: "This feature or item is not available on the connected backend.",
    413: "The submitted content is too large.",
    422: "Some submitted information is invalid.",
  };
  const message = messages[status] ?? (status >= 500 ? "The service is temporarily unavailable." : "The request could not be completed.");
  return new ApiError(message, status, `Request failed with HTTP ${status}. Sensitive server details are hidden.`);
}

function buildHeaders(options: RequestInit, isForm: boolean): Headers {
  const headers = new Headers(options.headers);
  if (!isForm && options.body !== undefined && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (!headers.has("Accept")) headers.set("Accept", "application/json");
  const token = window.sessionStorage.getItem(TOKEN_KEY);
  if (token && !headers.has("Authorization")) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

async function request<T>(path: string, options: RequestInit = {}, isForm = false): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: buildHeaders(options, isForm),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("Unable to reach the service. Check your connection and try again.", 0);
  }

  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent("coding-validation:session-expired", { detail: { from: window.location.pathname } }));
  }
  if (!response.ok) throw safeError(response.status);
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) return await response.json() as T;
  return await response.text() as T;
}

export const apiClient = {
  get: <T>(path: string, signal?: AbortSignal): Promise<T> => request<T>(path, { method: "GET", signal }),
  post: <T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> => request<T>(path, { method: "POST", body: JSON.stringify(body), signal }),
  patch: <T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> => request<T>(path, { method: "PATCH", body: JSON.stringify(body), signal }),
  delete: <T>(path: string, signal?: AbortSignal): Promise<T> => request<T>(path, { method: "DELETE", signal }),
  postForm: <T>(path: string, body: FormData, signal?: AbortSignal): Promise<T> => request<T>(path, { method: "POST", body, signal }, true),
};

export function apiBaseUrl(): string {
  return API_BASE_URL;
}

export function dispatchWorkspaceClear(): void {
  window.dispatchEvent(new Event("coding-validation:clear-user-data"));
}
