"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeftIcon, PlusIcon, Users } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import type { Coworker, Project } from "@/lib/types";

export default function ProjectDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const projectId = params.id;

  const [project, setProject] = useState<Project | null>(null);
  const [coworkers, setCoworkers] = useState<Coworker[]>([]);
  const [toAttach, setToAttach] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  async function loadProject() {
    setProject(await apiFetch<Project>(`/projects/${projectId}`));
  }

  useEffect(() => {
    if (!getTokens()) {
      router.push("/login");
      return;
    }
    void (async () => {
      try {
        const workspaceId = await getWorkspaceId();
        const [proj, cws] = await Promise.all([
          apiFetch<Project>(`/projects/${projectId}`),
          workspaceId
            ? apiFetch<Coworker[]>(`/workspaces/${workspaceId}/coworkers`)
            : Promise.resolve<Coworker[]>([]),
        ]);
        setProject(proj);
        setCoworkers(cws);
      } catch (err) {
        setError(err instanceof ApiRequestError ? err.message : "Couldn't load this project.");
      } finally {
        setLoading(false);
      }
    })();
  }, [projectId, router]);

  const attachedIds = new Set(
    (project?.resources ?? [])
      .filter((resource) => resource.resource_type === "coworker")
      .map((resource) => resource.resource_id),
  );
  const attached = coworkers.filter((coworker) => attachedIds.has(coworker.id));
  const available = coworkers.filter((coworker) => !attachedIds.has(coworker.id));

  async function attachCoworker() {
    if (!toAttach || busy) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/projects/${projectId}/resources`, {
        method: "POST",
        body: JSON.stringify({ resource_type: "coworker", resource_id: toAttach }),
      });
      setToAttach("");
      await loadProject();
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn't add that coworker.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <p className="mx-auto max-w-4xl px-4 py-10 text-sm text-muted-foreground">Loading…</p>;
  }

  if (!project) {
    return (
      <div className="mx-auto w-full max-w-4xl px-4 py-10">
        <Alert variant="destructive">
          <AlertDescription>{error ?? "Project not found."}</AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-4 py-10 sm:px-6">
      <Link
        href="/projects"
        className="flex w-fit items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeftIcon className="size-4" />
        Projects
      </Link>

      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{project.name}</h1>
          <Badge variant="outline" className="capitalize">
            {project.status}
          </Badge>
        </div>
        {project.description ? (
          <p className="max-w-2xl text-sm text-muted-foreground">{project.description}</p>
        ) : null}
      </div>

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <Users className="size-4" />
            Coworkers on this project
          </CardTitle>
          <Badge variant="outline">{attached.length}</Badge>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {attached.length === 0 ? (
            <p className="text-sm text-muted-foreground">No coworkers assigned yet.</p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {attached.map((coworker) => (
                <li
                  key={coworker.id}
                  className="flex items-center gap-3 rounded-lg border border-border px-3 py-2.5"
                >
                  <span className="flex size-8 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                    {coworker.name.charAt(0).toUpperCase()}
                  </span>
                  <Link
                    href={`/coworkers/${coworker.id}`}
                    className="truncate text-sm font-medium hover:underline"
                  >
                    {coworker.name}
                  </Link>
                </li>
              ))}
            </ul>
          )}

          {available.length > 0 ? (
            <div className="flex items-end gap-2 border-t border-border pt-4">
              <div className="flex flex-1 flex-col gap-1.5">
                <label className="text-sm font-medium" htmlFor="attach-coworker">
                  Add a coworker
                </label>
                <Select value={toAttach} onValueChange={setToAttach}>
                  <SelectTrigger id="attach-coworker" className="w-full">
                    <SelectValue placeholder="Choose a coworker" />
                  </SelectTrigger>
                  <SelectContent>
                    {available.map((coworker) => (
                      <SelectItem key={coworker.id} value={coworker.id}>
                        {coworker.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button disabled={busy || !toAttach} onClick={() => void attachCoworker()}>
                <PlusIcon data-icon="inline-start" />
                Add
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
