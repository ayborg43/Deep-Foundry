// Thin fetch helper for the Agentarium API. Attaches the bearer access
// token (if any) and normalizes the { error: { code, message, details } }
// envelope into a thrown ApiRequestError. No retry/refresh interceptor
// chain by design — out of scope for Milestone 1.

import { getTokens } from "./auth";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type ApiErrorBody = {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
  };
};

export class ApiRequestError extends Error {
  status: number;
  code: string;
  details?: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const tokens = getTokens();
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  if (tokens?.access) {
    headers.set("Authorization", `Bearer ${tokens.access}`);
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/v1${path}`, {
      ...options,
      headers,
    });
  } catch {
    throw new ApiRequestError(
      0,
      "network_error",
      "Couldn't reach the server. Check your connection and try again."
    );
  }

  if (res.status === 204 || res.status === 205) {
    return undefined as T;
  }

  const raw = await res.text();
  const data = raw ? (JSON.parse(raw) as unknown) : null;

  if (!res.ok) {
    const body = (data ?? {}) as ApiErrorBody;
    throw new ApiRequestError(
      res.status,
      body.error?.code ?? "unknown_error",
      body.error?.message ?? "Something went wrong. Please try again.",
      body.error?.details
    );
  }

  return data as T;
}
