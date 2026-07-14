"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ShieldCheckIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import { RISK_BADGE_CLASS, RISK_LABELS } from "@/lib/coworkers";
import type { ApprovalRequestData } from "@/lib/types";

export default function ApprovalsPage() {
  const router = useRouter();
  const [items, setItems] = useState<ApprovalRequestData[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  async function load() {
    const workspace = await getWorkspaceId();
    if (!workspace) return;
    setItems(
      await apiFetch<ApprovalRequestData[]>(
        `/workspaces/${workspace}/approval-requests?status=pending`
      )
    );
    setIsLoading(false);
  }

  useEffect(() => {
    if (!getTokens()) {
      router.push("/login");
      return;
    }
    const initial = window.setTimeout(() => {
      void load().catch((err) => {
        setIsLoading(false);
        setError(err instanceof ApiRequestError ? err.message : "Couldn't load approvals.");
      });
    }, 0);
    const timer = window.setInterval(() => void load(), 15_000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [router]);

  async function decide(item: ApprovalRequestData, approve: boolean) {
    setBusyId(item.id);
    setError(null);
    try {
      await apiFetch(`/approval-requests/${item.id}/${approve ? "approve" : "deny"}`, {
        method: "POST",
      });
      setItems((current) => current.filter((candidate) => candidate.id !== item.id));
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn't record decision.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-4 py-12">
      <div>
        <h1 id="approval-inbox-heading" className="text-xl font-semibold">
          Approval inbox
        </h1>
        <p className="text-sm text-muted-foreground">
          Workspace-wide actions waiting for your decision.
        </p>
      </div>
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <section aria-labelledby="approval-inbox-heading" aria-busy={isLoading}>
        {isLoading ? (
          <p role="status" className="text-sm text-muted-foreground">
            Loading approvals...
          </p>
        ) : items.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
              <ShieldCheckIcon className="size-10 text-muted-foreground" aria-hidden="true" />
              <p className="font-medium">Nothing needs approval</p>
              <p className="text-sm text-muted-foreground">
                Blocked coworker actions will appear here.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="flex flex-col gap-3">
            {items.map((item) => {
              const risk = item.tool_risk_classification;
              const titleId = `approval-${item.id}-title`;
              const actor = item.coworker_name ?? "Coworker";
              return (
                <Card key={item.id}>
                  <CardContent
                    className="flex flex-col gap-3"
                    role="article"
                    aria-labelledby={titleId}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <div className="flex items-center gap-2">
                          <h2 id={titleId} className="font-medium">
                            {actor} wants to run {item.tool_name}
                          </h2>
                          {risk ? (
                            <Badge className={RISK_BADGE_CLASS[risk]}>{RISK_LABELS[risk]}</Badge>
                          ) : null}
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {item.task_title ? `Task: ${item.task_title}` : "Conversation action"} ·{" "}
                          {new Date(item.created_at).toLocaleString()}
                        </p>
                      </div>
                      {item.task_id ? (
                        <Button asChild size="sm" variant="outline">
                          <Link
                            href={`/tasks/${item.task_id}`}
                            aria-label={`View context for ${item.tool_name}`}
                          >
                            Context
                          </Link>
                        </Button>
                      ) : null}
                    </div>
                    <pre
                      className="overflow-x-auto rounded-lg bg-muted p-3 text-xs"
                      tabIndex={0}
                      aria-label={`${item.tool_name} arguments`}
                    >
                      {JSON.stringify(item.requested_action.arguments ?? {}, null, 2)}
                    </pre>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        disabled={busyId === item.id}
                        onClick={() => void decide(item, true)}
                        aria-label={`Approve ${item.tool_name} for ${actor}`}
                      >
                        Approve
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        disabled={busyId === item.id}
                        onClick={() => void decide(item, false)}
                        aria-label={`Deny ${item.tool_name} for ${actor}`}
                      >
                        Deny
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}
