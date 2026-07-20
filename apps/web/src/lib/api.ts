// Thin fetch helper for the Deep-Foundry API. Attaches the bearer access
// token (if any) and normalizes the { error: { code, message, details } }
// envelope into a thrown ApiRequestError. No retry/refresh interceptor
// chain by design — out of scope for Milestone 1.

import { getTokens } from "./auth";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

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

// `auth: false` skips the bearer header for public endpoints (login,
// register, refresh). A stale token in localStorage would otherwise be
// sent and rejected by JWTAuthentication before the AllowAny view runs.
type ApiFetchOptions = RequestInit & { auth?: boolean };

export async function apiFetch<T = unknown>(
  path: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  const { auth = true, ...init } = options;
  const tokens = getTokens();
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (auth && tokens?.access) {
    headers.set("Authorization", `Bearer ${tokens.access}`);
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/v1${path}`, {
      ...init,
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

export async function apiDownload(path: string, fallbackName: string): Promise<void> {
  const tokens = getTokens();
  const headers = new Headers();
  if (tokens?.access) headers.set("Authorization", `Bearer ${tokens.access}`);
  const response = await fetch(`${API_BASE_URL}/api/v1${path}`, { headers });
  if (!response.ok) {
    let message = "Couldn't download this file.";
    try {
      const body = (await response.json()) as ApiErrorBody & { detail?: string };
      message = body.error?.message ?? body.detail ?? message;
    } catch {
      // Keep the safe fallback for non-JSON proxy errors.
    }
    throw new ApiRequestError(response.status, "download_failed", message);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filename = /filename="?([^";]+)"?/i.exec(disposition)?.[1] ?? fallbackName;
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}
