"use client";

import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { RISK_BADGE_CLASS, RISK_LABELS } from "@/lib/coworkers";
import type { AttachedTool, RiskClassification, Tool } from "@/lib/types";

// Safe first, then sensitive, then dangerous — so the low-friction capabilities
// a coworker most often needs (search, read) surface at the top.
const RISK_ORDER: Record<RiskClassification, number> = {
  safe: 0,
  sensitive: 1,
  dangerous: 2,
};

// Inline capability manager: attach or remove catalog tools for an existing
// coworker without leaving the screen you're on. The backend re-reads a
// coworker's attached tools at the start of every turn, so a tool added here is
// usable on the coworker's very next reply.
export function CoworkerToolsDialog({
  open,
  onOpenChange,
  coworkerId,
  coworkerName,
  attachedTools,
  allTools,
  onAttachedChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  coworkerId: string;
  coworkerName: string;
  attachedTools: AttachedTool[];
  allTools: Tool[];
  onAttachedChange: (next: AttachedTool[]) => void;
}) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const attachedIds = new Set(attachedTools.map((t) => t.id));
  const toolById = new Map(allTools.map((t) => [t.id, t]));
  const available = allTools
    .filter((t) => !attachedIds.has(t.id))
    .sort(
      (a, b) =>
        RISK_ORDER[a.risk_classification] - RISK_ORDER[b.risk_classification] ||
        a.name.localeCompare(b.name)
    );

  async function attach(tool: Tool) {
    setBusyId(tool.id);
    setError(null);
    try {
      await apiFetch(`/coworkers/${coworkerId}/tools`, {
        method: "POST",
        body: JSON.stringify({ tool_id: tool.id }),
      });
      onAttachedChange([...attachedTools, { id: tool.id, name: tool.name, enabled: true }]);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn't add that tool.");
    } finally {
      setBusyId(null);
    }
  }

  async function detach(toolId: string) {
    setBusyId(toolId);
    setError(null);
    try {
      await apiFetch(`/coworkers/${coworkerId}/tools/${toolId}`, { method: "DELETE" });
      onAttachedChange(attachedTools.filter((t) => t.id !== toolId));
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn't remove that tool.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] gap-4 overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{coworkerName}&apos;s tools</DialogTitle>
          <DialogDescription>
            Add a capability and {coworkerName} can use it on its next reply. Sensitive
            and dangerous tools still ask for your approval before running.
          </DialogDescription>
        </DialogHeader>

        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        <div className="flex flex-col gap-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Attached
          </p>
          {attachedTools.length === 0 ? (
            <p className="text-sm text-muted-foreground">No tools yet — add some below.</p>
          ) : (
            <ul className="flex flex-col divide-y rounded-lg border">
              {attachedTools.map((t) => {
                const full = toolById.get(t.id);
                return (
                  <li key={t.id} className="flex items-center justify-between gap-3 px-3 py-2">
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="truncate text-sm font-medium">{t.name}</span>
                      {full ? (
                        <Badge className={RISK_BADGE_CLASS[full.risk_classification]}>
                          {RISK_LABELS[full.risk_classification]}
                        </Badge>
                      ) : null}
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={busyId === t.id}
                      onClick={() => detach(t.id)}
                    >
                      {busyId === t.id ? "Removing…" : "Remove"}
                    </Button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Add a tool
          </p>
          {available.length === 0 ? (
            <p className="text-sm text-muted-foreground">Every available tool is attached.</p>
          ) : (
            <ul className="flex flex-col divide-y rounded-lg border">
              {available.map((tool) => (
                <li
                  key={tool.id}
                  className="flex items-start justify-between gap-3 px-3 py-2"
                >
                  <span className="flex min-w-0 flex-col gap-0.5">
                    <span className="flex items-center gap-2">
                      <span className="text-sm font-medium">{tool.name}</span>
                      <Badge className={RISK_BADGE_CLASS[tool.risk_classification]}>
                        {RISK_LABELS[tool.risk_classification]}
                      </Badge>
                    </span>
                    <span className="truncate text-xs text-muted-foreground">
                      {tool.description}
                    </span>
                  </span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={busyId === tool.id}
                    onClick={() => attach(tool)}
                  >
                    {busyId === tool.id ? "Adding…" : "Add"}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
