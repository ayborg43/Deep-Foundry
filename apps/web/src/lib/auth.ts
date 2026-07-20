// Browser session storage and timeout helpers. Tokens are mirrored to
// localStorage for refreshes and shared across tabs; the session guard and API
// client use the activity timestamp and JWT expiry to end stale sessions.

import type { Workspace } from "./types";

export type Tokens = {
  access: string;
  refresh: string;
};

const ACCESS_KEY = "deep-foundry.tokens.access";
const REFRESH_KEY = "deep-foundry.tokens.refresh";
const WORKSPACE_ID_KEY = "deep-foundry.workspace_id";
const LEGACY_ACCESS_KEY = "agentarium.tokens.access";
const LEGACY_REFRESH_KEY = "agentarium.tokens.refresh";
const LEGACY_WORKSPACE_ID_KEY = "agentarium.workspace_id";
const SESSION_ACTIVITY_KEY = "deep-foundry.session.last_activity";

export const AUTH_SESSION_CHANGED_EVENT = "deep-foundry:auth-session-changed";

const configuredTimeoutMinutes = Number(
  process.env.NEXT_PUBLIC_SESSION_IDLE_TIMEOUT_MINUTES ?? "30"
);
export const SESSION_IDLE_TIMEOUT_MS =
  Number.isFinite(configuredTimeoutMinutes) && configuredTimeoutMinutes > 0
    ? Math.min(configuredTimeoutMinutes, 7 * 24 * 60) * 60_000
    : 30 * 60_000;

let memoryTokens: Tokens | null = null;

function notifySessionChanged(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(AUTH_SESSION_CHANGED_EVENT));
  }
}

function jwtExpiresAt(token: string): number | null {
  if (typeof window === "undefined") return null;
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const decoded = JSON.parse(
      window.atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "="))
    ) as { exp?: number };
    return typeof decoded.exp === "number" ? decoded.exp * 1000 : null;
  } catch {
    return null;
  }
}

export function touchSession(): void {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(SESSION_ACTIVITY_KEY, String(Date.now()));
  }
}

export function setTokens(tokens: Tokens, options: { touch?: boolean } = {}): void {
  memoryTokens = tokens;
  if (typeof window !== "undefined") {
    window.localStorage.setItem(ACCESS_KEY, tokens.access);
    window.localStorage.setItem(REFRESH_KEY, tokens.refresh);
    if (options.touch !== false) touchSession();
    notifySessionChanged();
  }
}

export function getTokens(): Tokens | null {
  if (typeof window === "undefined") {
    return memoryTokens;
  }
  const storedAccess = window.localStorage.getItem(ACCESS_KEY);
  const storedRefresh = window.localStorage.getItem(REFRESH_KEY);
  const access = storedAccess ?? window.localStorage.getItem(LEGACY_ACCESS_KEY);
  const refresh = storedRefresh ?? window.localStorage.getItem(LEGACY_REFRESH_KEY);
  if (!access || !refresh) {
    memoryTokens = null;
    return null;
  }
  const refreshExpiresAt = jwtExpiresAt(refresh);
  if (refreshExpiresAt !== null && refreshExpiresAt <= Date.now()) {
    clearTokens();
    return null;
  }
  if (
    !memoryTokens ||
    memoryTokens.access !== access ||
    memoryTokens.refresh !== refresh
  ) {
    memoryTokens = { access, refresh };
  }
  if (!storedAccess) window.localStorage.setItem(ACCESS_KEY, access);
  if (!storedRefresh) window.localStorage.setItem(REFRESH_KEY, refresh);
  if (!window.localStorage.getItem(SESSION_ACTIVITY_KEY)) touchSession();
  return memoryTokens;
}

export function getSessionRemainingMs(): number | null {
  const tokens = getTokens();
  if (!tokens || typeof window === "undefined") return null;
  const lastActivity = Number(window.localStorage.getItem(SESSION_ACTIVITY_KEY));
  const idleDeadline =
    Number.isFinite(lastActivity) && lastActivity > 0
      ? lastActivity + SESSION_IDLE_TIMEOUT_MS
      : Date.now() + SESSION_IDLE_TIMEOUT_MS;
  const refreshDeadline = jwtExpiresAt(tokens.refresh);
  return Math.min(idleDeadline, refreshDeadline ?? Number.POSITIVE_INFINITY) - Date.now();
}

export function expireSession(): void {
  clearTokens();
  if (typeof window === "undefined") return;
  const pathname = window.location.pathname;
  if (pathname.startsWith("/login") || pathname.startsWith("/signup")) return;
  window.location.replace("/login?reason=session_expired");
}

export function clearTokens(): void {
  memoryTokens = null;
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(ACCESS_KEY);
    window.localStorage.removeItem(REFRESH_KEY);
    window.localStorage.removeItem(WORKSPACE_ID_KEY);
    window.localStorage.removeItem(LEGACY_ACCESS_KEY);
    window.localStorage.removeItem(LEGACY_REFRESH_KEY);
    window.localStorage.removeItem(LEGACY_WORKSPACE_ID_KEY);
    window.localStorage.removeItem(SESSION_ACTIVITY_KEY);
    notifySessionChanged();
  }
}

// --- Workspace id ------------------------------------------------------
// We persist the workspace id we're given at signup/OAuth time. For users
// who log back in on a fresh browser (no localStorage entry) — plain
// /auth/login and /auth/mfa/verify return just { tokens }, with no
// workspace — we fall back to GET /workspaces and use the first entry.
// At Milestone 1 scope every user has exactly one workspace (their
// personal workspace), so that response is always a one-item array;
// multi-workspace UI is out of scope (see ROADMAP.md). If neither source
// has it, callers should show an explanatory empty state rather than
// crash.

export function setWorkspaceId(id: string): void {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(WORKSPACE_ID_KEY, id);
  }
}

// Synchronous read of the persisted active workspace, without the network
// fallback getWorkspaceId does. Used by the workspace switcher to highlight the
// current selection immediately on mount.
export function getStoredWorkspaceId(): string | null {
  if (typeof window === "undefined") return null;
  return (
    window.localStorage.getItem(WORKSPACE_ID_KEY) ??
    window.localStorage.getItem(LEGACY_WORKSPACE_ID_KEY)
  );
}

export async function getWorkspaceId(): Promise<string | null> {
  if (typeof window !== "undefined") {
    const stored =
      window.localStorage.getItem(WORKSPACE_ID_KEY) ??
      window.localStorage.getItem(LEGACY_WORKSPACE_ID_KEY);
    if (stored) return stored;
  }

  if (!getTokens()) {
    return null;
  }

  try {
    const { apiFetch } = await import("./api");
    const workspaces = await apiFetch<Workspace[]>("/workspaces");
    const id = workspaces[0]?.id ?? null;
    if (id) {
      setWorkspaceId(id);
    }
    return id;
  } catch {
    return null;
  }
}
