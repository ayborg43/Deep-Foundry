// Shared fetch helper for the Deep-Foundry API. It attaches the bearer access
// token, performs one refresh-and-retry on 401, redirects expired sessions to
// login, and normalizes the API error envelope into ApiRequestError.

import {
  expireSession,
  getSessionRemainingMs,
  getTokens,
  setTokens,
  type Tokens,
} from "./auth";

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

let refreshPromise: Promise<Tokens | null> | null = null;

async function refreshSession(): Promise<Tokens | null> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    const current = getTokens();
    if (!current?.refresh) {
      expireSession();
      return null;
    }
    let response: Response;
    try {
      response = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh: current.refresh }),
      });
    } catch {
      return null;
    }
    if (!response.ok) {
      const latest = getTokens();
      if (latest?.refresh && latest.refresh !== current.refresh) return latest;
      expireSession();
      return null;
    }
    try {
      const data = (await response.json()) as { access?: string; refresh?: string };
      if (!data.access) {
        expireSession();
        return null;
      }
      const refreshed = {
        access: data.access,
        refresh: data.refresh ?? current.refresh,
      };
      // Background polling must not count as user activity.
      setTokens(refreshed, { touch: false });
      return refreshed;
    } catch {
      expireSession();
      return null;
    }
  })();
  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

export async function fetchWithSession(
  path: string,
  options: ApiFetchOptions = {}
): Promise<Response> {
  const { auth = true, ...init } = options;
  if (auth) {
    const remaining = getSessionRemainingMs();
    if (remaining !== null && remaining <= 0) {
      expireSession();
      throw new ApiRequestError(
        401,
        "session_expired",
        "Your session expired. Sign in again to continue."
      );
    }
  }

  const request = (access?: string) => {
    const headers = new Headers(init.headers);
    if (!headers.has("Content-Type") && init.body && !(init.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
    if (auth && access) headers.set("Authorization", `Bearer ${access}`);
    return fetch(`${API_BASE_URL}/api/v1${path}`, { ...init, headers });
  };

  const current = auth ? getTokens() : null;
  let response = await request(current?.access);
  if (!auth || response.status !== 401) return response;

  const refreshed = await refreshSession();
  if (!refreshed) return response;
  response = await request(refreshed.access);
  if (response.status === 401) expireSession();
  return response;
}

export async function apiFetch<T = unknown>(
  path: string,
  options: ApiFetchOptions = {}
): Promise<T> {
  let res: Response;
  try {
    res = await fetchWithSession(path, options);
  } catch (error) {
    if (error instanceof ApiRequestError) throw error;
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
  let response: Response;
  try {
    response = await fetchWithSession(path);
  } catch (error) {
    if (error instanceof ApiRequestError) throw error;
    throw new ApiRequestError(
      0,
      "network_error",
      "Couldn't reach the server. Check your connection and try again."
    );
  }
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
