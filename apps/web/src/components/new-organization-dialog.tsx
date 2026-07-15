"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Building2, SparklesIcon, UsersIcon } from "lucide-react";

import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { setWorkspaceId } from "@/lib/auth";

type TeamTemplate = {
  key: string;
  label: string;
  description: string;
  coworkers: { name: string; role_description: string }[];
};

type SpecCoworker = {
  name: string;
  team_role: string;
  custom_role_label?: string;
  role_description: string;
  tools: string[];
};

type TeamSpec = {
  team_name: string;
  collaboration_pattern: string;
  coworkers: SpecCoworker[];
};

// "empty" = no coworkers; "ai" = describe it and review the proposal;
// anything else is a template key from GET /team-templates.
const EMPTY = "empty";
const AI = "ai";

export function NewOrganizationDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [name, setName] = useState("");
  const [templates, setTemplates] = useState<TeamTemplate[]>([]);
  const [choice, setChoice] = useState("solo");
  const [description, setDescription] = useState("");
  const [spec, setSpec] = useState<TeamSpec | null>(null);
  const [included, setIncluded] = useState<boolean[]>([]);
  const [suggesting, setSuggesting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // If the org was created but provisioning failed, remember it so a retry
  // provisions into the same org instead of creating a duplicate.
  const [createdOrgId, setCreatedOrgId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    void (async () => {
      try {
        setTemplates(await apiFetch<TeamTemplate[]>("/team-templates"));
      } catch {
        // Templates are an enhancement; without them the empty option remains.
      }
    })();
  }, [open]);

  function reset() {
    setName("");
    setChoice("solo");
    setDescription("");
    setSpec(null);
    setIncluded([]);
    setError(null);
    setCreatedOrgId(null);
    setBusy(false);
    setSuggesting(false);
  }

  async function suggest(orgless = true) {
    if (!description.trim() || suggesting) return;
    setSuggesting(true);
    setError(null);
    try {
      // Suggestions need a workspace for the provider credential; before the
      // org exists we use the current workspace's key (same self-hosted
      // instance), falling back with a clear message if none is configured.
      const workspaceId = orgless
        ? (await apiFetch<{ id: string }[]>("/workspaces"))[0]?.id
        : createdOrgId;
      if (!workspaceId) throw new ApiRequestError(0, "no_workspace", "No workspace available.");
      const proposal = await apiFetch<TeamSpec>(
        `/workspaces/${workspaceId}/team-suggestions`,
        { method: "POST", body: JSON.stringify({ description: description.trim() }) }
      );
      setSpec(proposal);
      setIncluded(proposal.coworkers.map(() => true));
    } catch (err) {
      setError(
        err instanceof ApiRequestError ? err.message : "Couldn't design a team. Try again."
      );
    } finally {
      setSuggesting(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim() || busy) return;
    if (choice === AI && (!spec || !included.some(Boolean))) {
      setError("Generate a team proposal and keep at least one coworker — or pick a template.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      let orgId = createdOrgId;
      if (!orgId) {
        const org = await apiFetch<{ id: string }>("/organizations", {
          method: "POST",
          body: JSON.stringify({ name: name.trim() }),
        });
        orgId = org.id;
        setCreatedOrgId(orgId);
      }
      if (choice !== EMPTY) {
        const body =
          choice === AI && spec
            ? {
                team_name: spec.team_name,
                collaboration_pattern: spec.collaboration_pattern,
                coworkers: spec.coworkers.filter((_, i) => included[i]),
              }
            : { template: choice };
        await apiFetch(`/workspaces/${orgId}/provision-team`, {
          method: "POST",
          body: JSON.stringify(body),
        });
      }
      setWorkspaceId(orgId);
      window.location.assign("/home");
    } catch (err) {
      setError(
        err instanceof ApiRequestError
          ? `${err.message}${createdOrgId ? " The organization was created — retrying only re-runs team setup." : ""}`
          : "Couldn't finish setting up the organization."
      );
      setBusy(false);
    }
  }

  const optionClass = (selected: boolean) =>
    `flex w-full flex-col gap-0.5 rounded-lg border px-3 py-2.5 text-left transition-colors ${
      selected
        ? "border-primary/50 bg-primary/5 ring-1 ring-primary/30"
        : "border-border hover:bg-accent"
    }`;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) reset();
      }}
    >
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>New organization</DialogTitle>
            <DialogDescription>
              A separate workspace for a company or team — its own coworkers, members, data,
              and settings. Pick a starting team and we&apos;ll set it up for you.
            </DialogDescription>
          </DialogHeader>

          <div className="my-4 flex flex-col gap-4">
            {error ? (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            ) : null}

            <div className="flex flex-col gap-2">
              <Label htmlFor="org_name">Organization name</Label>
              <Input
                id="org_name"
                autoFocus
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Acme Inc."
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label>Starting team</Label>
              <div role="radiogroup" aria-label="Starting team" className="grid gap-2">
                {templates.map((template) => (
                  <button
                    key={template.key}
                    type="button"
                    role="radio"
                    aria-checked={choice === template.key}
                    onClick={() => setChoice(template.key)}
                    className={optionClass(choice === template.key)}
                  >
                    <span className="flex items-center gap-2 text-sm font-medium">
                      <UsersIcon className="size-3.5 text-primary" />
                      {template.label}
                      <span className="ml-auto text-xs text-muted-foreground">
                        {template.coworkers.length} coworker{template.coworkers.length === 1 ? "" : "s"}
                      </span>
                    </span>
                    <span className="text-xs text-muted-foreground">{template.description}</span>
                  </button>
                ))}
                <button
                  type="button"
                  role="radio"
                  aria-checked={choice === AI}
                  onClick={() => setChoice(AI)}
                  className={optionClass(choice === AI)}
                >
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <SparklesIcon className="size-3.5 text-primary" />
                    Design it for me
                  </span>
                  <span className="text-xs text-muted-foreground">
                    Describe the company and AI proposes a team you can review.
                  </span>
                </button>
                <button
                  type="button"
                  role="radio"
                  aria-checked={choice === EMPTY}
                  onClick={() => setChoice(EMPTY)}
                  className={optionClass(choice === EMPTY)}
                >
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <Building2 className="size-3.5 text-muted-foreground" />
                    Empty workspace
                  </span>
                  <span className="text-xs text-muted-foreground">Start from scratch; add coworkers yourself.</span>
                </button>
              </div>
            </div>

            {choice === AI ? (
              <div className="flex flex-col gap-2 rounded-lg border border-border bg-muted/40 p-3">
                <Label htmlFor="org_description">What does this organization do?</Label>
                <Textarea
                  id="org_description"
                  rows={3}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="e.g. A 5-person design studio doing brand identity work for startups."
                />
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  className="w-fit"
                  disabled={suggesting || !description.trim()}
                  onClick={() => void suggest()}
                >
                  <SparklesIcon data-icon="inline-start" />
                  {suggesting ? "Designing…" : spec ? "Regenerate proposal" : "Suggest a team"}
                </Button>

                {spec ? (
                  <div className="mt-1 flex flex-col gap-1.5">
                    <p className="text-xs font-medium text-muted-foreground">
                      Proposed: {spec.team_name} — uncheck anyone you don&apos;t want.
                    </p>
                    {spec.coworkers.map((coworker, index) => (
                      <label
                        key={`${coworker.name}-${index}`}
                        className="flex items-start gap-2.5 rounded-md border border-border bg-background px-2.5 py-2"
                      >
                        <input
                          type="checkbox"
                          checked={included[index] ?? true}
                          onChange={(event) =>
                            setIncluded((current) =>
                              current.map((value, i) => (i === index ? event.target.checked : value))
                            )
                          }
                          className="mt-0.5 accent-[var(--primary)]"
                        />
                        <span className="min-w-0">
                          <span className="block text-sm font-medium leading-tight">
                            {coworker.name}
                            <span className="ml-1.5 text-xs font-normal text-muted-foreground">
                              {coworker.custom_role_label || coworker.team_role.replace(/_/g, " ")}
                            </span>
                          </span>
                          <span className="mt-0.5 line-clamp-2 block text-xs text-muted-foreground">
                            {coworker.role_description}
                          </span>
                        </span>
                      </label>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="ghost" disabled={busy}>
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={busy || !name.trim()}>
              {busy ? "Setting up…" : "Create organization"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
