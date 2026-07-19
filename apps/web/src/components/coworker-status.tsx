"use client";

import { AlertTriangleIcon, BanIcon, FlagIcon, Loader2Icon } from "lucide-react";

import { COWORKER_STATUS_META } from "@/lib/coworker-status";
import type { CoworkerStatusState } from "@/lib/types";

// Compact per-state icon for tight spots (the sidebar roster).
export function CoworkerStatusGlyph({
  state,
  className = "size-3.5",
}: {
  state: CoworkerStatusState;
  className?: string;
}) {
  const label = COWORKER_STATUS_META[state].label;
  switch (state) {
    case "working":
      return <Loader2Icon aria-label={label} className={`animate-spin text-primary ${className}`} />;
    case "needs_approval":
      return <FlagIcon aria-label={label} className={`text-amber-600 dark:text-amber-400 ${className}`} />;
    case "blocked":
      return <BanIcon aria-label={label} className={`text-muted-foreground ${className}`} />;
    case "error":
      return <AlertTriangleIcon aria-label={label} className={`text-destructive ${className}`} />;
    case "idle":
      return (
        <span
          aria-label={label}
          className="inline-block size-2 shrink-0 rounded-full bg-emerald-500"
        />
      );
  }
}

export function CoworkerStatusChip({ state }: { state: CoworkerStatusState }) {
  const meta = COWORKER_STATUS_META[state];
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${meta.chip}`}
    >
      {state === "working" ? <Loader2Icon className="size-3 animate-spin" /> : null}
      {state === "needs_approval" ? <FlagIcon className="size-3" /> : null}
      {state === "blocked" ? <BanIcon className="size-3" /> : null}
      {state === "error" ? <AlertTriangleIcon className="size-3" /> : null}
      {state === "idle" ? <span className="size-1.5 rounded-full bg-emerald-500" /> : null}
      {meta.label}
    </span>
  );
}
