"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { apiFetch, ApiRequestError } from "@/lib/api";

// Numeric (or numeric-string) argument fields of the request being
// approved, one level deep — the candidates for a threshold condition.
function numericPaths(args: Record<string, unknown>): { path: string; value: number }[] {
  const found: { path: string; value: number }[] = [];
  const visit = (value: unknown, path: string) => {
    if (typeof value === "boolean") return;
    const num =
      typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
    if (!Number.isNaN(num) && (typeof value === "number" || value !== "")) {
      found.push({ path, value: num });
      return;
    }
    if (value !== null && typeof value === "object" && !Array.isArray(value) && path.split(".").length < 2) {
      for (const [key, child] of Object.entries(value)) visit(child, path ? `${path}.${key}` : key);
    }
  };
  for (const [key, value] of Object.entries(args)) visit(value, key);
  return found;
}

type PolicyTarget = {
  workspaceId: string;
  coworkerId: string;
  coworkerName: string;
  toolId: string;
  toolName: string;
  args: Record<string, unknown>;
};

function PolicyForm({
  target,
  onClose,
  onCreated,
}: {
  target: PolicyTarget;
  onClose: () => void;
  onCreated?: () => void;
}) {
  // Mounted fresh each time the dialog opens (keyed by the parent), so
  // useState initializers are the reset mechanism — no effects needed.
  const [candidates] = useState(() => numericPaths(target.args));
  const [mode, setMode] = useState<"always" | "under">(() =>
    numericPaths(target.args).length > 0 ? "under" : "always"
  );
  const [path, setPath] = useState(() => numericPaths(target.args)[0]?.path ?? "");
  const [maxAmount, setMaxAmount] = useState(() => {
    const first = numericPaths(target.args)[0];
    return first ? String(first.value) : "";
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/workspaces/${target.workspaceId}/approval-policies`, {
        method: "POST",
        body: JSON.stringify({
          tool_id: target.toolId,
          coworker_id: target.coworkerId,
          ...(mode === "under" ? { argument_path: path, max_amount: maxAmount } : {}),
        }),
      });
      onClose();
      onCreated?.();
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn't create the policy.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>
          Always allow <span className="font-mono">{target.toolName}</span>
        </DialogTitle>
        <DialogDescription>
          Creates a standing policy for {target.coworkerName}: matching {target.toolName}{" "}
          calls run without asking you. You can remove it any time from the approvals page.
        </DialogDescription>
      </DialogHeader>

      <div className="flex flex-col gap-2 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="radio"
            name="policy-mode"
            checked={mode === "always"}
            onChange={() => setMode("always")}
          />
          Always allow, no conditions
        </label>
        {candidates.length > 0 ? (
          <label className="flex flex-wrap items-center gap-2">
            <input
              type="radio"
              name="policy-mode"
              checked={mode === "under"}
              onChange={() => setMode("under")}
            />
            Only when
            <select
              value={path}
              onChange={(e) => setPath(e.target.value)}
              disabled={mode !== "under"}
              aria-label="Argument field"
              className="rounded-md border bg-background px-2 py-1 font-mono text-xs"
            >
              {candidates.map((candidate) => (
                <option key={candidate.path} value={candidate.path}>
                  {candidate.path}
                </option>
              ))}
            </select>
            is at most
            <Input
              value={maxAmount}
              onChange={(e) => setMaxAmount(e.target.value)}
              disabled={mode !== "under"}
              inputMode="decimal"
              aria-label="Maximum amount"
              className="h-8 w-24"
            />
          </label>
        ) : null}
      </div>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      <DialogFooter>
        <Button variant="outline" onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button
          onClick={() => void submit()}
          disabled={busy || (mode === "under" && (!path || !maxAmount.trim()))}
        >
          {busy ? "Creating…" : "Create policy"}
        </Button>
      </DialogFooter>
    </>
  );
}

export function ApprovalPolicyDialog({
  open,
  onOpenChange,
  onCreated,
  ...target
}: PolicyTarget & {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        {open ? (
          <PolicyForm
            key={target.toolId}
            target={target}
            onClose={() => onOpenChange(false)}
            onCreated={onCreated}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
