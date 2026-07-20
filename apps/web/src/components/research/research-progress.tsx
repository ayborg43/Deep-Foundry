import { CheckCircle2Icon, CircleIcon, LoaderCircleIcon, XCircleIcon } from "lucide-react";

import type { ResearchStep } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ResearchProgress({
  progress,
  stage,
  steps,
}: {
  progress: number;
  stage: string;
  steps: ResearchStep[];
}) {
  return (
    <section aria-label="Research progress" aria-live="polite" className="grid gap-3">
      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="font-medium capitalize">{stage.replaceAll("_", " ")}</span>
        <span className="tabular-nums text-muted-foreground">{progress}%</span>
      </div>
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={progress}
        className="h-2 overflow-hidden rounded-full bg-muted"
      >
        <div className="h-full rounded-full bg-primary transition-[width] duration-500" style={{ width: `${progress}%` }} />
      </div>
      {steps.length ? (
        <ol className="grid gap-2">
          {steps.map((step) => {
            const Icon =
              step.status === "completed" ? CheckCircle2Icon :
              step.status === "running" ? LoaderCircleIcon :
              step.status === "failed" ? XCircleIcon : CircleIcon;
            return (
              <li key={step.id} className="flex items-start gap-2 text-sm">
                <Icon
                  className={cn(
                    "mt-0.5 size-4 shrink-0",
                    step.status === "running" && "animate-spin text-primary",
                    step.status === "completed" && "text-emerald-600",
                    step.status === "failed" && "text-destructive",
                    step.status === "pending" && "text-muted-foreground",
                  )}
                />
                <span className={step.status === "pending" ? "text-muted-foreground" : ""}>{step.message}</span>
              </li>
            );
          })}
        </ol>
      ) : null}
    </section>
  );
}
