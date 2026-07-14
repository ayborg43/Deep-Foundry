import type { TaskStatus } from "@/lib/types";

// Semantic status pill for background tasks. Colors read against both light
// and dark surfaces; "Working" carries a live pulsing dot.
const STATUS: Record<TaskStatus, { label: string; className: string; dot?: boolean }> = {
  pending: {
    label: "Pending",
    className: "bg-muted text-muted-foreground",
  },
  in_progress: {
    label: "Working",
    className: "bg-primary/12 text-primary",
    dot: true,
  },
  needs_approval: {
    label: "Needs approval",
    className: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  },
  blocked: {
    label: "Blocked",
    className: "bg-destructive/12 text-destructive",
  },
  completed: {
    label: "Completed",
    className: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  },
  failed: {
    label: "Failed",
    className: "bg-destructive/12 text-destructive",
  },
};

export function StatusBadge({ status }: { status: TaskStatus }) {
  const s = STATUS[status];
  return (
    <span
      className={`inline-flex h-6 w-fit shrink-0 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium ${s.className}`}
    >
      {s.dot ? (
        <span className="relative flex size-1.5">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-current opacity-60" />
          <span className="relative inline-flex size-1.5 rounded-full bg-current" />
        </span>
      ) : null}
      {s.label}
    </span>
  );
}
