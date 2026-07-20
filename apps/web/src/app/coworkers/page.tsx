"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BotIcon, BrainIcon, CpuIcon, PlusIcon, WrenchIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CoworkerStatusChip } from "@/components/coworker-status";
import { PageHeader } from "@/components/page-header";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import { COWORKER_STATUS_META, timeAgo, useCoworkerStatuses } from "@/lib/coworker-status";
import { MODEL_SHORT_LABELS } from "@/lib/coworkers";
import type { Coworker, MemoryEntry } from "@/lib/types";

// No blue — the product color system deliberately excludes it.
const ACCENTS = [
  { bar: "bg-emerald-500", avatar: "bg-emerald-500/12 text-emerald-600 dark:text-emerald-400" },
  { bar: "bg-rose-500", avatar: "bg-rose-500/12 text-rose-600 dark:text-rose-400" },
  { bar: "bg-amber-500", avatar: "bg-amber-500/12 text-amber-600 dark:text-amber-400" },
  { bar: "bg-teal-500", avatar: "bg-teal-500/12 text-teal-600 dark:text-teal-400" },
  { bar: "bg-violet-500", avatar: "bg-violet-500/12 text-violet-600 dark:text-violet-400" },
  { bar: "bg-orange-500", avatar: "bg-orange-500/12 text-orange-600 dark:text-orange-400" },
] as const;

// Deterministic per-coworker accent: same coworker, same color, every render
// and every device, with no stored color field needed.
function accentOf(id: string) {
  let hash = 0;
  for (const char of id) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return ACCENTS[hash % ACCENTS.length];
}

export default function CoworkersRosterPage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [coworkers, setCoworkers] = useState<Coworker[]>([]);
  const [memoryCounts, setMemoryCounts] = useState<Record<string, number>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const statuses = useCoworkerStatuses(workspaceId, 15_000);

  useEffect(() => {
    if (!getTokens()) {
      router.push("/login");
      return;
    }

    // Reads localStorage, falling back to GET /workspaces — only
    // resolvable post-mount, matching the Milestone 1 settings screens.
    async function load() {
      const id = await getWorkspaceId();
      setWorkspaceId(id);

      if (!id) {
        setIsLoading(false);
        return;
      }

      try {
        const data = await apiFetch<Coworker[]>(`/workspaces/${id}/coworkers`);
        setCoworkers(data);

        // Memory counts are decoration on the card footer — fetched in
        // parallel after the roster renders, and any failure just leaves
        // that coworker's count blank.
        void Promise.allSettled(
          data.map(async (coworker) => {
            const entries = await apiFetch<MemoryEntry[]>(
              `/memory/coworker/${coworker.id}/timeline`
            );
            return [coworker.id, entries.length] as const;
          })
        ).then((results) => {
          const counts: Record<string, number> = {};
          for (const result of results) {
            if (result.status === "fulfilled") counts[result.value[0]] = result.value[1];
          }
          setMemoryCounts(counts);
        });
      } catch (err) {
        setError(
          err instanceof ApiRequestError
            ? err.message
            : "Couldn't load your coworkers."
        );
      } finally {
        setIsLoading(false);
      }
    }

    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-8 px-4 py-10 sm:px-6">
      <PageHeader
        eyebrow="Workspace"
        title="Coworkers"
        description={
          coworkers.length > 0
            ? `${coworkers.length} teammate${coworkers.length === 1 ? "" : "s"} on this instance · persistent memory, schedules, and permissions`
            : "Persistent AI coworkers with their own role, model, memory, and tools — always on, always yours."
        }
        actions={
          coworkers.length > 0 ? (
            <Button asChild>
              <Link href="/coworkers/new">
                <PlusIcon data-icon="inline-start" />
                Hire a coworker
              </Link>
            </Button>
          ) : null
        }
      />

      {!workspaceId && !isLoading ? (
        <Alert variant="destructive">
          <AlertDescription>
            Couldn&apos;t determine your current workspace. Try logging out and
            back in, or sign up again if this is a fresh session.
          </AlertDescription>
        </Alert>
      ) : null}

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : coworkers.length === 0 && workspaceId ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <div className="flex size-14 items-center justify-center rounded-2xl bg-primary/12 text-primary">
              <BotIcon className="size-7" />
            </div>
            <div>
              <p className="font-heading text-lg font-semibold">No coworkers yet</p>
              <p className="text-sm text-muted-foreground">
                Create your first coworker to give it a role, a model, and
                tools it can use.
              </p>
            </div>
            <Button asChild>
              <Link href="/coworkers/new">
                <PlusIcon data-icon="inline-start" />
                Create your first coworker
              </Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {coworkers.map((coworker) => {
            const accent = accentOf(coworker.id);
            const status = statuses.get(coworker.id);
            const panelText =
              status === undefined
                ? null
                : status.state === "idle"
                  ? status.last_run_at
                    ? `Idle — last ran “${status.last_run_title}” ${timeAgo(status.last_run_at)}`
                    : null
                  : status.detail || null;
            return (
              <Link key={coworker.id} href={`/coworkers/${coworker.id}`} className="group/card">
                <Card className="h-full overflow-hidden pt-0 transition-all group-hover/card:border-primary/40 group-hover/card:shadow-sm">
                  <div className={`h-1 w-full ${accent.bar}`} aria-hidden="true" />
                  <CardHeader className="flex-row items-center gap-3">
                    {coworker.avatar_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={coworker.avatar_url}
                        alt=""
                        className="size-10 shrink-0 rounded-full object-cover"
                      />
                    ) : (
                      <div
                        className={`flex size-10 shrink-0 items-center justify-center rounded-full ${accent.avatar}`}
                      >
                        <BotIcon className="size-5" />
                      </div>
                    )}
                    <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
                      <CardTitle className="truncate">{coworker.name}</CardTitle>
                      {status ? <CoworkerStatusChip state={status.state} /> : null}
                    </div>
                  </CardHeader>
                  <CardContent className="flex flex-1 flex-col gap-3">
                    <p className="line-clamp-2 text-sm text-muted-foreground">
                      {coworker.role_description}
                    </p>
                    {status && panelText ? (
                      <div className="flex-1 rounded-lg border bg-muted/40 px-3 py-2">
                        <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                          {COWORKER_STATUS_META[status.state].panel}
                        </p>
                        <p className="line-clamp-2 text-xs leading-relaxed">{panelText}</p>
                      </div>
                    ) : (
                      <div className="flex-1" />
                    )}
                    <div className="flex items-center gap-3 border-t pt-3 text-xs text-muted-foreground">
                      <span className="inline-flex min-w-0 items-center gap-1">
                        <CpuIcon className="size-3 shrink-0" />
                        <span className="truncate font-mono">
                          {MODEL_SHORT_LABELS[coworker.model_binding.primary] ??
                            coworker.model_binding.primary}
                        </span>
                      </span>
                      <span className="inline-flex shrink-0 items-center gap-1">
                        <BrainIcon className="size-3" />
                        {memoryCounts[coworker.id] ?? "—"}
                      </span>
                      <span className="inline-flex shrink-0 items-center gap-1">
                        <WrenchIcon className="size-3" />
                        {coworker.attached_tools.length}{" "}
                        {coworker.attached_tools.length === 1 ? "tool" : "tools"}
                      </span>
                    </div>
                  </CardContent>
                </Card>
              </Link>
            );
          })}

          <Link
            href="/coworkers/new"
            className="flex min-h-48 flex-col items-center justify-center gap-3 rounded-xl border border-dashed p-6 text-center transition-colors hover:border-primary/50 hover:bg-accent/40"
          >
            <span className="flex size-11 items-center justify-center rounded-xl border bg-background text-muted-foreground">
              <PlusIcon className="size-5" />
            </span>
            <span className="font-heading font-semibold">Hire a coworker</span>
            <span className="max-w-52 text-sm text-muted-foreground">
              Describe the job you need done and configure the role.
            </span>
          </Link>
        </div>
      )}
    </div>
  );
}
