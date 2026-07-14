"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { PlusIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import type { BackgroundTask, Coworker } from "@/lib/types";

export default function TasksPage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [tasks, setTasks] = useState<BackgroundTask[]>([]);
  const [coworkers, setCoworkers] = useState<Coworker[]>([]);
  const [coworkerId, setCoworkerId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load(workspace: string) {
    const [taskData, coworkerData] = await Promise.all([
      apiFetch<BackgroundTask[]>(`/tasks?workspace_id=${workspace}`),
      apiFetch<Coworker[]>(`/workspaces/${workspace}/coworkers`),
    ]);
    setTasks(taskData);
    setCoworkers(coworkerData);
    setCoworkerId((current) => current || coworkerData[0]?.id || "");
  }

  useEffect(() => {
    if (!getTokens()) { router.push("/login"); return; }
    void (async () => {
      const workspace = await getWorkspaceId();
      setWorkspaceId(workspace);
      if (!workspace) return;
      try { await load(workspace); }
      catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn't load tasks."); }
    })();
  }, [router]);

  async function createTask() {
    if (!workspaceId || !coworkerId || !title.trim() || !description.trim()) return;
    setBusy(true); setError(null);
    try {
      const task = await apiFetch<BackgroundTask>("/tasks", {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspaceId, coworker_id: coworkerId, title, description }),
      });
      router.push(`/tasks/${task.id}`);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn't create task.");
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-4 py-10 sm:px-6">
      <PageHeader
        eyebrow="Workspace"
        title="Tasks"
        description="Hand work to a coworker and walk away. It runs in the background and comes back when it's done — or when it needs your approval to proceed."
      />
      {error ? <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert> : null}
      <Card>
        <CardHeader><CardTitle className="font-heading text-lg">New task</CardTitle></CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5"><Label htmlFor="task-coworker">Coworker</Label><Select value={coworkerId} onValueChange={setCoworkerId}><SelectTrigger id="task-coworker" className="w-full"><SelectValue placeholder="Choose a coworker" /></SelectTrigger><SelectContent>{coworkers.map((coworker) => <SelectItem key={coworker.id} value={coworker.id}>{coworker.name}</SelectItem>)}</SelectContent></Select></div>
          <div className="flex flex-col gap-1.5"><Label htmlFor="task-title">Title</Label><Input id="task-title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Prepare the weekly summary" /></div>
          <div className="flex flex-col gap-1.5 sm:col-span-2"><Label htmlFor="task-description">Instructions</Label><Textarea id="task-description" rows={4} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Describe the outcome, constraints, and source material." /></div>
          <Button className="w-fit" disabled={busy || !coworkerId || !title.trim() || !description.trim()} onClick={createTask}><PlusIcon data-icon="inline-start" />{busy ? "Queuing..." : "Assign task"}</Button>
        </CardContent>
      </Card>
      <div className="flex flex-col gap-2.5">
        {tasks.length === 0 ? (
          <Card><CardContent className="py-12 text-center text-sm text-muted-foreground">No background tasks yet. Assign one above to get started.</CardContent></Card>
        ) : (
          tasks.map((task) => (
            <Link key={task.id} href={`/tasks/${task.id}`} className="group/task">
              <Card className="transition-all group-hover/task:border-primary/40 group-hover/task:shadow-sm">
                <CardContent className="flex items-center justify-between gap-4 py-4">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{task.title}</p>
                    <p className="text-xs text-muted-foreground">{task.coworker_name} · {new Date(task.created_at).toLocaleString()}</p>
                  </div>
                  <StatusBadge status={task.status} />
                </CardContent>
              </Card>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}
