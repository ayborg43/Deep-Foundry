"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { FolderIcon, PlusIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader } from "@/components/page-header";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import type { Project } from "@/lib/types";

export default function ProjectsPage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  async function load(id: string) {
    setProjects(await apiFetch<Project[]>(`/projects?workspace_id=${id}`));
  }

  useEffect(() => {
    if (!getTokens()) {
      router.push("/login");
      return;
    }
    void (async () => {
      const id = await getWorkspaceId();
      if (!id) {
        setLoading(false);
        return;
      }
      setWorkspaceId(id);
      try {
        await load(id);
      } catch (err) {
        setError(err instanceof ApiRequestError ? err.message : "Couldn't load projects.");
      } finally {
        setLoading(false);
      }
    })();
  }, [router]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await apiFetch("/projects", {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspaceId, name: name.trim(), description: description.trim() }),
      });
      setName("");
      setDescription("");
      await load(workspaceId);
    } catch (err) {
      setError(
        err instanceof ApiRequestError
          ? err.message
          : "Couldn't create the project.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-4 py-10 sm:px-6">
      <PageHeader
        title="Projects"
        description="Group coworkers and work under a shared goal, so related tasks and conversations live in one place."
      />

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardContent className="pt-6">
          <form onSubmit={create} className="flex flex-col gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="project-name">Project name</Label>
              <Input
                id="project-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Q3 launch"
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="project-description">Description (optional)</Label>
              <Textarea
                id="project-description"
                rows={2}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="What this project is for."
              />
            </div>
            <Button className="w-fit" disabled={busy || !name.trim()}>
              <PlusIcon data-icon="inline-start" />
              {busy ? "Creating…" : "Create project"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : projects.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
            <span className="flex size-11 items-center justify-center rounded-full bg-secondary text-muted-foreground">
              <FolderIcon className="size-5" />
            </span>
            <p className="text-sm font-medium">No projects yet</p>
            <p className="text-sm text-muted-foreground">Create one above to organize coworkers and work.</p>
          </CardContent>
        </Card>
      ) : (
        <ul className="flex flex-col gap-2.5">
          {projects.map((project) => (
            <li key={project.id}>
              <Link href={`/projects/${project.id}`} className="group/row block">
                <Card className="transition-all group-hover/row:border-primary/40 group-hover/row:shadow-[var(--shadow-sm)]">
                  <CardContent className="flex items-center gap-3 py-3.5">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-secondary text-muted-foreground transition-colors group-hover/row:text-foreground">
                      <FolderIcon className="size-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{project.name}</p>
                      {project.description ? (
                        <p className="truncate text-xs text-muted-foreground">{project.description}</p>
                      ) : null}
                    </div>
                    <Badge variant="outline" className="capitalize">
                      {project.status}
                    </Badge>
                  </CardContent>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
