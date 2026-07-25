"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CheckIcon, CreditCardIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import type { Subscription, SubscriptionPlan } from "@/lib/types";

const USAGE_ROWS: { key: keyof Subscription["usage"]; label: string; limitKey: keyof SubscriptionPlan }[] = [
  { key: "coworkers", label: "Coworkers", limitKey: "max_coworkers" },
  { key: "agent_teams", label: "Agent teams", limitKey: "max_agent_teams" },
  { key: "tasks_per_month", label: "Tasks this month", limitKey: "max_tasks_per_month" },
  { key: "seats", label: "Workspace members", limitKey: "max_seats" },
];

function UsageBar({ used, limit }: { used: number; limit: number | null }) {
  if (limit === null) {
    return (
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
        <div className="h-full w-full rounded-full bg-primary/40" />
      </div>
    );
  }
  const ratio = limit > 0 ? Math.min(1, used / limit) : 1;
  const atLimit = used >= limit;
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
      <div
        className={`h-full rounded-full ${atLimit ? "bg-destructive" : "bg-primary"}`}
        style={{ width: `${Math.round(ratio * 100)}%` }}
      />
    </div>
  );
}

export default function BillingSettingsPage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [plans, setPlans] = useState<SubscriptionPlan[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [switchingKey, setSwitchingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load(id: string) {
    const [sub, catalog] = await Promise.all([
      apiFetch<Subscription>(`/workspaces/${id}/subscription`),
      apiFetch<SubscriptionPlan[]>("/plans"),
    ]);
    setSubscription(sub);
    setPlans(catalog);
  }

  useEffect(() => {
    if (!getTokens()) {
      router.push("/login");
      return;
    }
    void (async () => {
      const id = await getWorkspaceId();
      setWorkspaceId(id);
      if (!id) {
        setIsLoading(false);
        return;
      }
      try {
        await load(id);
      } catch (err) {
        setError(err instanceof ApiRequestError ? err.message : "Couldn't load billing details.");
      } finally {
        setIsLoading(false);
      }
    })();
  }, [router]);

  async function switchPlan(plan: SubscriptionPlan) {
    if (!workspaceId || switchingKey) return;
    setSwitchingKey(plan.key);
    setError(null);
    try {
      await apiFetch(`/workspaces/${workspaceId}/subscription`, {
        method: "PATCH",
        body: JSON.stringify({ plan_key: plan.key }),
      });
      await load(workspaceId);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn't switch plans.");
    } finally {
      setSwitchingKey(null);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-4 py-10 sm:px-6">
      <PageHeader
        title="Billing & plan"
        description="What this workspace is on, how much of it you've used, and what else is available."
      />

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {isLoading ? (
        <div className="h-40 animate-pulse rounded-xl border border-border bg-card" />
      ) : (
        <>
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <CardTitle className="flex items-center gap-2">
                  <CreditCardIcon className="size-4.5 text-primary" />
                  Current plan
                </CardTitle>
                {subscription?.plan ? (
                  <Badge variant="outline" className="capitalize">
                    {subscription.plan.name}
                  </Badge>
                ) : null}
              </div>
            </CardHeader>
            <CardContent className="flex flex-col gap-6">
              {subscription?.plan ? (
                <p className="text-sm text-muted-foreground">
                  {subscription.plan.description || "No description."}
                </p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No plan is configured for this workspace yet.
                </p>
              )}

              {subscription ? (
                <div className="grid gap-4 sm:grid-cols-2">
                  {USAGE_ROWS.map((row) => {
                    const used = subscription.usage[row.key];
                    const limit = subscription.plan ? subscription.plan[row.limitKey] : null;
                    const normalizedLimit = typeof limit === "number" ? limit : null;
                    return (
                      <div key={row.key} className="flex flex-col gap-1.5">
                        <div className="flex items-baseline justify-between text-sm">
                          <span className="text-muted-foreground">{row.label}</span>
                          <span className="font-medium tabular-nums">
                            {used} {normalizedLimit === null ? "" : `/ ${normalizedLimit}`}
                            {normalizedLimit === null ? (
                              <span className="ml-1 text-muted-foreground">Unlimited</span>
                            ) : null}
                          </span>
                        </div>
                        <UsageBar used={used} limit={normalizedLimit} />
                      </div>
                    );
                  })}
                </div>
              ) : null}
            </CardContent>
          </Card>

          <section aria-label="Available plans" className="flex flex-col gap-3">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Available plans
            </h2>
            <div className="grid gap-4 sm:grid-cols-3">
              {plans.map((plan) => {
                const isCurrent = subscription?.plan?.id === plan.id;
                return (
                  <Card key={plan.id} className={isCurrent ? "border-primary/50 ring-1 ring-primary/20" : ""}>
                    <CardHeader>
                      <CardTitle className="flex items-baseline justify-between text-base">
                        {plan.name}
                        <span className="text-sm font-normal text-muted-foreground">
                          {Number(plan.price_usd) > 0 ? `$${plan.price_usd}/mo` : "Free"}
                        </span>
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="flex flex-col gap-4">
                      <p className="text-xs text-muted-foreground">{plan.description}</p>
                      <ul className="flex flex-col gap-1.5 text-xs text-muted-foreground">
                        <li>{plan.max_coworkers ?? "Unlimited"} coworkers</li>
                        <li>{plan.max_agent_teams ?? "Unlimited"} agent teams</li>
                        <li>{plan.max_tasks_per_month ?? "Unlimited"} tasks / month</li>
                        <li>{plan.max_seats ?? "Unlimited"} members</li>
                      </ul>
                      <Button
                        size="sm"
                        variant={isCurrent ? "outline" : "default"}
                        disabled={isCurrent || switchingKey !== null}
                        onClick={() => void switchPlan(plan)}
                      >
                        {isCurrent ? (
                          <>
                            <CheckIcon data-icon="inline-start" />
                            Current plan
                          </>
                        ) : switchingKey === plan.key ? (
                          "Switching..."
                        ) : (
                          "Switch to this plan"
                        )}
                      </Button>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
