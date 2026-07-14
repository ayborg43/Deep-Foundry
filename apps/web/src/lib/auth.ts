// Minimal token storage helper for Milestone 1.
// Keeps tokens in memory for the life of the tab and mirrors them to
// localStorage so a refresh doesn't immediately log the user out.
// Intentionally NOT a full auth context/provider — see apps/web AGENTS.md
// scope notes for Milestone 1.

import { apiFetch } from "./api";
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

let memoryTokens: Tokens | null = null;

export function setTokens(tokens: Tokens): void {
  memoryTokens = tokens;
  if (typeof window !== "undefined") {
    window.localStorage.setItem(ACCESS_KEY, tokens.access);
    window.localStorage.setItem(REFRESH_KEY, tokens.refresh);
  }
}

export function getTokens(): Tokens | null {
  if (memoryTokens) {
    return memoryTokens;
  }
  if (typeof window === "undefined") {
    return null;
  }
  const access =
    window.localStorage.getItem(ACCESS_KEY) ??
    window.localStorage.getItem(LEGACY_ACCESS_KEY);
  const refresh =
    window.localStorage.getItem(REFRESH_KEY) ??
    window.localStorage.getItem(LEGACY_REFRESH_KEY);
  if (!access || !refresh) {
    return null;
  }
  memoryTokens = { access, refresh };
  setTokens(memoryTokens);
  return memoryTokens;
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
