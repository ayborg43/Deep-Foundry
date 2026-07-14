"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { BotIcon, PlusIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import { MODEL_SHORT_LABELS } from "@/lib/coworkers";
import type { Coworker } from "@/lib/types";

export default function CoworkersRosterPage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [coworkers, setCoworkers] = useState<Coworker[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
        description="Persistent AI coworkers with their own role, model, memory, and tools — always on, always yours."
        actions={
          coworkers.length > 0 ? (
            <Button asChild>
              <Link href="/coworkers/new">
                <PlusIcon data-icon="inline-start" />
                New coworker
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
          {coworkers.map((coworker) => (
            <Link key={coworker.id} href={`/coworkers/${coworker.id}`} className="group/card">
              <Card className="h-full transition-all group-hover/card:border-primary/40 group-hover/card:shadow-sm">
                <CardHeader className="flex-row items-center gap-3">
                  {coworker.avatar_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={coworker.avatar_url}
                      alt=""
                      className="size-10 shrink-0 rounded-full object-cover"
                    />
                  ) : (
                    <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary/12 text-primary">
                      <BotIcon className="size-5" />
                    </div>
                  )}
                  <div className="flex min-w-0 flex-col">
                    <CardTitle className="truncate">{coworker.name}</CardTitle>
                    <span className="text-xs text-muted-foreground">
                      {MODEL_SHORT_LABELS[coworker.model_binding.primary] ??
                        coworker.model_binding.primary}
                    </span>
                  </div>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <p className="line-clamp-2 text-sm text-muted-foreground">
                    {coworker.role_description}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {coworker.attached_tools.length === 0 ? (
                      <span className="text-xs text-muted-foreground">
                        No tools attached
                      </span>
                    ) : (
                      coworker.attached_tools.map((tool) => (
                        <Badge key={tool.id} variant="outline">
                          {tool.name}
                        </Badge>
                      ))
                    )}
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
