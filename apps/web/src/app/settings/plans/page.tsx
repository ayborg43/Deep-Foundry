"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { PlusIcon, ShieldAlertIcon, StarIcon, Trash2Icon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/page-header";
import { Switch } from "@/components/ui/switch";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens } from "@/lib/auth";
import type { SubscriptionPlan, User } from "@/lib/types";

// Blank in a limit input means "unlimited" — mirrors SubscriptionPlan's
// null-means-unlimited convention on the backend.
type Draft = {
  key: string;
  name: string;
  description: string;
  price_usd: string;
  max_coworkers: string;
  max_agent_teams: string;
  max_tasks_per_month: string;
  max_seats: string;
  sort_order: string;
  is_default: boolean;
  active: boolean;
};

const BLANK_DRAFT: Draft = {
  key: "", name: "", description: "", price_usd: "0",
  max_coworkers: "", max_agent_teams: "", max_tasks_per_month: "", max_seats: "",
  sort_order: "0", is_default: false, active: true,
};

function toPayload(draft: Draft) {
  const int = (v: string) => (v.trim() === "" ? null : Number(v));
  return {
    key: draft.key.trim(),
    name: draft.name.trim(),
    description: draft.description.trim(),
    price_usd: draft.price_usd.trim() || "0",
    max_coworkers: int(draft.max_coworkers),
    max_agent_teams: int(draft.max_agent_teams),
    max_tasks_per_month: int(draft.max_tasks_per_month),
    max_seats: int(draft.max_seats),
    sort_order: Number(draft.sort_order.trim() || "0"),
    is_default: draft.is_default,
    active: draft.active,
  };
}

function planToDraft(plan: SubscriptionPlan): Draft {
  const str = (v: number | null) => (v === null ? "" : String(v));
  return {
    key: plan.key, name: plan.name, description: plan.description,
    price_usd: plan.price_usd,
    max_coworkers: str(plan.max_coworkers), max_agent_teams: str(plan.max_agent_teams),
    max_tasks_per_month: str(plan.max_tasks_per_month), max_seats: str(plan.max_seats),
    sort_order: String(plan.sort_order ?? 0),
    is_default: plan.is_default, active: plan.active,
  };
}

function LimitField({
  label, value, onChange,
}: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="grid gap-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <Input
        type="number"
        min={0}
        placeholder="Unlimited"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

function PlanForm({
  draft, onChange, onSubmit, busy, submitLabel, keyEditable, savedAt,
}: {
  draft: Draft;
  onChange: (draft: Draft) => void;
  onSubmit: (event: FormEvent) => void;
  busy: boolean;
  submitLabel: string;
  // The key identifies the plan to everything that references it by string
  // (self-serve plan switching, integrations) — editable only at creation,
  // frozen afterward so an admin can't quietly break those references.
  keyEditable: boolean;
  savedAt: number | null;
}) {
  return (
    <form onSubmit={onSubmit} className="grid gap-4">
      <div className="grid gap-4 sm:grid-cols-4">
        <div className="grid gap-1.5">
          <Label className="text-xs text-muted-foreground">Key (slug)</Label>
          <Input
            value={draft.key}
            onChange={(e) => onChange({ ...draft, key: e.target.value })}
            placeholder="pro"
            required
            disabled={!keyEditable}
            title={keyEditable ? undefined : "The key can't be changed after a plan is created."}
          />
        </div>
        <div className="grid gap-1.5">
          <Label className="text-xs text-muted-foreground">Name</Label>
          <Input
            value={draft.name}
            onChange={(e) => onChange({ ...draft, name: e.target.value })}
            placeholder="Pro"
            required
          />
        </div>
        <div className="grid gap-1.5">
          <Label className="text-xs text-muted-foreground">Price (USD / month)</Label>
          <Input
            type="number"
            min={0}
            step="0.01"
            value={draft.price_usd}
            onChange={(e) => onChange({ ...draft, price_usd: e.target.value })}
          />
        </div>
        <div className="grid gap-1.5">
          <Label className="text-xs text-muted-foreground">Sort order</Label>
          <Input
            type="number"
            value={draft.sort_order}
            onChange={(e) => onChange({ ...draft, sort_order: e.target.value })}
          />
        </div>
      </div>
      <div className="grid gap-1.5">
        <Label className="text-xs text-muted-foreground">Description</Label>
        <Input
          value={draft.description}
          onChange={(e) => onChange({ ...draft, description: e.target.value })}
          placeholder="Shown to users choosing a plan"
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-4">
        <LimitField label="Max coworkers" value={draft.max_coworkers} onChange={(v) => onChange({ ...draft, max_coworkers: v })} />
        <LimitField label="Max agent teams" value={draft.max_agent_teams} onChange={(v) => onChange({ ...draft, max_agent_teams: v })} />
        <LimitField label="Max tasks / month" value={draft.max_tasks_per_month} onChange={(v) => onChange({ ...draft, max_tasks_per_month: v })} />
        <LimitField label="Max seats" value={draft.max_seats} onChange={(v) => onChange({ ...draft, max_seats: v })} />
      </div>
      <div className="flex flex-wrap items-center gap-6">
        <label className="flex items-center gap-2 text-sm">
          <Switch checked={draft.active} onCheckedChange={(v) => onChange({ ...draft, active: v })} />
          Active (selectable by workspaces)
        </label>
        <label className="flex items-center gap-2 text-sm">
          <Switch checked={draft.is_default} onCheckedChange={(v) => onChange({ ...draft, is_default: v })} />
          Default for new workspaces
        </label>
      </div>
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={busy} className="w-fit">
          {busy ? "Saving..." : submitLabel}
        </Button>
        {savedAt ? <span className="text-xs text-muted-foreground">Saved</span> : null}
      </div>
    </form>
  );
}

export default function PlanCatalogAdminPage() {
  const router = useRouter();
  const [authorized, setAuthorized] = useState<boolean | null>(null);
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [newDraft, setNewDraft] = useState<Draft>(BLANK_DRAFT);
  const [editDrafts, setEditDrafts] = useState<Record<string, Draft>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [savedIds, setSavedIds] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const rows = await apiFetch<SubscriptionPlan[]>("/admin/plans");
    setPlans(rows);
    setEditDrafts(Object.fromEntries(rows.map((plan) => [plan.id, planToDraft(plan)])));
  }

  useEffect(() => {
    if (!getTokens()) {
      router.push("/login");
      return;
    }
    void (async () => {
      try {
        const me = await apiFetch<User>("/me");
        if (!me.is_staff) {
          setAuthorized(false);
          return;
        }
        setAuthorized(true);
        await load();
      } catch (err) {
        setAuthorized(false);
        setError(err instanceof ApiRequestError ? err.message : "Couldn't load the plan catalog.");
      }
    })();
  }, [router]);

  async function createPlan(event: FormEvent) {
    event.preventDefault();
    setBusyId("new");
    setError(null);
    try {
      await apiFetch("/admin/plans", { method: "POST", body: JSON.stringify(toPayload(newDraft)) });
      setNewDraft(BLANK_DRAFT);
      await load();
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn't create that plan.");
    } finally {
      setBusyId(null);
    }
  }

  async function savePlan(plan: SubscriptionPlan, event: FormEvent) {
    event.preventDefault();
    const draft = editDrafts[plan.id];
    if (!draft) return;
    setBusyId(plan.id);
    setError(null);
    try {
      await apiFetch(`/admin/plans/${plan.id}`, {
        method: "PATCH",
        body: JSON.stringify(toPayload(draft)),
      });
      await load();
      const savedAt = Date.now();
      setSavedIds((current) => ({ ...current, [plan.id]: savedAt }));
      setTimeout(
        () =>
          setSavedIds((current) =>
            current[plan.id] === savedAt ? { ...current, [plan.id]: 0 } : current
          ),
        2000
      );
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn't save that plan.");
    } finally {
      setBusyId(null);
    }
  }

  async function deletePlan(plan: SubscriptionPlan) {
    if (!window.confirm(`Delete the "${plan.name}" plan? This only works if no workspace is subscribed to it.`)) return;
    setBusyId(plan.id);
    setError(null);
    try {
      await apiFetch(`/admin/plans/${plan.id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn't delete that plan.");
    } finally {
      setBusyId(null);
    }
  }

  if (authorized === false) {
    return (
      <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center gap-3 px-4 py-20 text-center">
        <ShieldAlertIcon className="size-8 text-muted-foreground" />
        <p className="text-sm font-medium">Platform staff only</p>
        <p className="text-sm text-muted-foreground">
          The plan catalog is managed by Deep-Foundry staff accounts.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-4 py-10 sm:px-6">
      <PageHeader
        title="Plan catalog"
        description="Every subscription plan workspaces can be on. Editing limits here applies immediately to every workspace already subscribed to that plan."
      />

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {authorized === null ? (
        <div className="h-40 animate-pulse rounded-xl border border-border bg-card" />
      ) : (
        <>
          <section className="flex flex-col gap-3">
            {plans.map((plan) => (
              <Card key={plan.id}>
                <CardHeader>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <CardTitle className="flex items-center gap-2 text-base">
                      {plan.name}
                      <span className="font-mono text-xs font-normal text-muted-foreground">
                        {plan.key}
                      </span>
                    </CardTitle>
                    <div className="flex items-center gap-2">
                      {plan.is_default ? (
                        <Badge variant="default" className="flex items-center gap-1">
                          <StarIcon className="size-3" />
                          Default
                        </Badge>
                      ) : null}
                      <Badge variant={plan.active ? "outline" : "secondary"}>
                        {plan.active ? "Active" : "Inactive"}
                      </Badge>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        className="text-muted-foreground hover:text-destructive"
                        aria-label={`Delete ${plan.name}`}
                        disabled={busyId === plan.id}
                        onClick={() => void deletePlan(plan)}
                      >
                        <Trash2Icon />
                      </Button>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <PlanForm
                    draft={editDrafts[plan.id] ?? planToDraft(plan)}
                    onChange={(draft) => setEditDrafts((current) => ({ ...current, [plan.id]: draft }))}
                    onSubmit={(event) => void savePlan(plan, event)}
                    busy={busyId === plan.id}
                    submitLabel="Save changes"
                    keyEditable={false}
                    savedAt={savedIds[plan.id] || null}
                  />
                </CardContent>
              </Card>
            ))}
          </section>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <PlusIcon className="size-4" />
                New plan
              </CardTitle>
            </CardHeader>
            <CardContent>
              <PlanForm
                draft={newDraft}
                onChange={setNewDraft}
                onSubmit={createPlan}
                busy={busyId === "new"}
                submitLabel="Create plan"
                keyEditable
                savedAt={null}
              />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
