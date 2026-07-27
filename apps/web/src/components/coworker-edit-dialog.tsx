"use client";

import { useState } from "react";
import { CheckIcon, SparklesIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { MODEL_OPTIONS, RISK_BADGE_CLASS, RISK_LABELS } from "@/lib/coworkers";
import type { Coworker, CoworkerEditProposal, ModelId, Tool } from "@/lib/types";

const RISK_ORDER: Record<string, number> = { safe: 0, sensitive: 1, dangerous: 2 };

// Edit a coworker two ways in one place: describe the change in plain English
// (the AI drafts it into the fields for you to review) or edit the fields
// directly. Nothing saves until you hit Save.
export function CoworkerEditDialog({
  open,
  onOpenChange,
  coworker,
  allTools,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  coworker: Coworker;
  allTools: Tool[];
  onSaved: (updated: Coworker) => void;
}) {
  const [name, setName] = useState(coworker.name);
  const [role, setRole] = useState(coworker.role_description);
  const [model, setModel] = useState<ModelId>(coworker.model_binding.primary);
  const [toolIds, setToolIds] = useState<Set<string>>(
    () => new Set(coworker.attached_tools.map((t) => t.id))
  );
  const [instruction, setInstruction] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // State is seeded from `coworker` at mount; parents mount this only while
  // open (and key it per coworker), so it always starts from current values.
  const toolsByName = new Map(allTools.map((t) => [t.name, t]));
  const sortedTools = [...allTools].sort(
    (a, b) =>
      RISK_ORDER[a.risk_classification] - RISK_ORDER[b.risk_classification] ||
      a.name.localeCompare(b.name)
  );

  function toggleTool(id: string) {
    setToolIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function draft() {
    const text = instruction.trim();
    if (!text) return;
    setDrafting(true);
    setError(null);
    setSummary(null);
    try {
      const proposal = await apiFetch<CoworkerEditProposal>(
        `/coworkers/${coworker.id}/suggest-edit`,
        { method: "POST", body: JSON.stringify({ instruction: text }) }
      );
      if (proposal.name) setName(proposal.name);
      if (proposal.role_description) setRole(proposal.role_description);
      if (proposal.model) setModel(proposal.model);
      if (proposal.add_tools?.length || proposal.remove_tools?.length) {
        setToolIds((current) => {
          const next = new Set(current);
          for (const toolName of proposal.add_tools ?? []) {
            const tool = toolsByName.get(toolName);
            if (tool) next.add(tool.id);
          }
          for (const toolName of proposal.remove_tools ?? []) {
            const tool = toolsByName.get(toolName);
            if (tool) next.delete(tool.id);
          }
          return next;
        });
      }
      setSummary(proposal.summary || "Drafted into the fields below — review and save.");
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn't draft that change.");
    } finally {
      setDrafting(false);
    }
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {};
      if (name.trim() && name !== coworker.name) body.name = name.trim();
      if (role.trim() && role !== coworker.role_description) body.role_description = role.trim();
      if (model !== coworker.model_binding.primary) body.model_binding = { primary: model };
      if (Object.keys(body).length > 0) {
        await apiFetch(`/coworkers/${coworker.id}`, { method: "PATCH", body: JSON.stringify(body) });
      }
      const currentIds = new Set(coworker.attached_tools.map((t) => t.id));
      const toAttach = [...toolIds].filter((id) => !currentIds.has(id));
      const toDetach = [...currentIds].filter((id) => !toolIds.has(id));
      await Promise.all([
        ...toAttach.map((id) =>
          apiFetch(`/coworkers/${coworker.id}/tools`, {
            method: "POST",
            body: JSON.stringify({ tool_id: id }),
          })
        ),
        ...toDetach.map((id) =>
          apiFetch(`/coworkers/${coworker.id}/tools/${id}`, { method: "DELETE" })
        ),
      ]);
      const fresh = await apiFetch<Coworker>(`/coworkers/${coworker.id}`);
      onSaved(fresh);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn't save changes.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] gap-4 overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Edit {coworker.name}</DialogTitle>
          <DialogDescription>
            Describe the change in plain English and let {coworker.name} draft it, or edit
            the fields directly. Nothing saves until you choose Save.
          </DialogDescription>
        </DialogHeader>

        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        {/* Conversational edit */}
        <div className="flex flex-col gap-1.5 rounded-lg border bg-muted/30 p-3">
          <Label htmlFor="edit-instruction" className="flex items-center gap-1.5">
            <SparklesIcon className="size-3.5 text-primary" />
            Describe the change
          </Label>
          <Textarea
            id="edit-instruction"
            rows={2}
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder="e.g. also handle invoices, switch to the pro model, and add web search"
          />
          <div className="flex items-center gap-2">
            <Button type="button" size="sm" variant="outline" disabled={drafting || !instruction.trim()} onClick={() => void draft()}>
              {drafting ? "Drafting…" : "Draft change"}
            </Button>
            {summary ? <span className="text-xs text-muted-foreground">{summary}</span> : null}
          </div>
        </div>

        {/* Manual fields — two columns on desktop, stacked on mobile */}
        <div className="grid gap-4 md:grid-cols-2">
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-name">Name</Label>
              <Input id="edit-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-model">Model</Label>
              <Select value={model} onValueChange={(v) => setModel(v as ModelId)}>
                <SelectTrigger id="edit-model" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MODEL_OPTIONS.map((option) => (
                    <SelectItem key={option.id} value={option.id}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-1 flex-col gap-1.5">
              <Label htmlFor="edit-role">Role description</Label>
              <Textarea
                id="edit-role"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="min-h-32 flex-1 md:min-h-48"
              />
            </div>
          </div>

          <div className="flex min-h-0 flex-col gap-1.5">
            <Label>Tools</Label>
            <ul className="flex max-h-72 flex-1 flex-col divide-y overflow-y-auto rounded-lg border md:max-h-none">
              {sortedTools.map((tool) => {
                const checked = toolIds.has(tool.id);
                return (
                  <li key={tool.id}>
                    <button
                      type="button"
                      onClick={() => toggleTool(tool.id)}
                      aria-pressed={checked}
                      className="flex w-full items-start gap-3 px-3 py-2 text-left transition-colors hover:bg-accent/40"
                    >
                      <span
                        className={`mt-0.5 flex size-4 shrink-0 items-center justify-center rounded border ${
                          checked ? "border-primary bg-primary text-primary-foreground" : "border-input"
                        }`}
                      >
                        {checked ? <CheckIcon className="size-3" /> : null}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-2">
                          <span className="text-sm font-medium">{tool.name}</span>
                          <Badge className={RISK_BADGE_CLASS[tool.risk_classification]}>
                            {RISK_LABELS[tool.risk_classification]}
                          </Badge>
                        </span>
                        <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                          {tool.description}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button type="button" onClick={() => void save()} disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
