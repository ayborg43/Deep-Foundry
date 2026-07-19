"use client";

import { useEffect, useState } from "react";

import { apiFetch } from "./api";
import type { CoworkerStatus, CoworkerStatusState } from "./types";

export const COWORKER_STATUS_META: Record<
  CoworkerStatusState,
  { label: string; chip: string; panel: string }
> = {
  working: {
    label: "Working",
    chip: "bg-primary/10 text-primary",
    panel: "Working on now",
  },
  needs_approval: {
    label: "Needs approval",
    chip: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-400",
    panel: "Waiting on you",
  },
  blocked: {
    label: "Blocked",
    chip: "bg-muted text-muted-foreground",
    panel: "Blocked on",
  },
  error: {
    label: "Error",
    chip: "bg-destructive/10 text-destructive",
    panel: "Error",
  },
  idle: {
    label: "Idle",
    chip: "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-400",
    panel: "Status",
  },
};

export function timeAgo(iso: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

// Polls the derived status feed; status is decoration everywhere it's
// shown, so failures just leave the map empty and the UI renders without.
export function useCoworkerStatuses(
  workspaceId: string | null,
  intervalMs = 20_000
): Map<string, CoworkerStatus> {
  const [statuses, setStatuses] = useState<Map<string, CoworkerStatus>>(new Map());

  useEffect(() => {
    if (!workspaceId) return;
    let cancelled = false;
    async function load() {
      try {
        const rows = await apiFetch<CoworkerStatus[]>(
          `/workspaces/${workspaceId}/coworkers/status`
        );
        if (!cancelled) setStatuses(new Map(rows.map((row) => [row.coworker_id, row])));
      } catch {
        // Keep whatever we had; the next poll may recover.
      }
    }
    void load();
    const timer = window.setInterval(() => void load(), intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [workspaceId, intervalMs]);

  return statuses;
}
