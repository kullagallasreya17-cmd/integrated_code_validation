import { apiClient, mocksEnabled } from "./client";
import type { AuthSession, Role } from "./types";

export interface LoginRequest {
  readonly email: string;
  readonly password: string;
}

export async function login(request: LoginRequest, signal?: AbortSignal): Promise<AuthSession> {
  if (mocksEnabled()) {
    const role: Role = request.email.toLowerCase().startsWith("admin") ? "Administrator" : "Developer";
    return { access_token: `mock-token-${crypto.randomUUID()}`, token_type: "Bearer", user: { id: `mock-user-${crypto.randomUUID()}`, email: request.email, full_name: request.email.split("@")[0], role } };
  }
  return apiClient.post<AuthSession>("/api/auth/login", request, signal);
}

export async function getCurrentUser(signal?: AbortSignal): Promise<AuthSession["user"]> {
  if (mocksEnabled()) throw new Error("Sign in using the mock login form to create a local mock session.");
  return apiClient.get<AuthSession["user"]>("/api/auth/me", signal);
}
