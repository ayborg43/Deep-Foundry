"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ClockIcon, PlusIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import type { BackgroundTask, Coworker, TaskStatus } from "@/lib/types";

const STATUS_LABEL: Record<TaskStatus, string> = {
  pending: "Pending",
  in_progress: "Working",
  needs_approval: "Needs approval",
  blocked: "Blocked",
  completed: "Completed",
  failed: "Failed",
};

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
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-4 py-12">
      <div><h1 className="text-xl font-semibold">Background tasks</h1><p className="text-sm text-muted-foreground">Assign work and return when your coworker finishes or needs approval.</p></div>
      {error ? <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert> : null}
      <Card>
        <CardHeader><CardTitle>New task</CardTitle></CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5"><Label htmlFor="task-coworker">Coworker</Label><Select value={coworkerId} onValueChange={setCoworkerId}><SelectTrigger id="task-coworker" className="w-full"><SelectValue placeholder="Choose a coworker" /></SelectTrigger><SelectContent>{coworkers.map((coworker) => <SelectItem key={coworker.id} value={coworker.id}>{coworker.name}</SelectItem>)}</SelectContent></Select></div>
          <div className="flex flex-col gap-1.5"><Label htmlFor="task-title">Title</Label><Input id="task-title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Prepare the weekly summary" /></div>
          <div className="flex flex-col gap-1.5 sm:col-span-2"><Label htmlFor="task-description">Instructions</Label><Textarea id="task-description" rows={4} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Describe the outcome, constraints, and source material." /></div>
          <Button className="w-fit" disabled={busy || !coworkerId || !title.trim() || !description.trim()} onClick={createTask}><PlusIcon data-icon="inline-start" />{busy ? "Queuing..." : "Assign task"}</Button>
        </CardContent>
      </Card>
      <div className="flex flex-col gap-3">
        {tasks.length === 0 ? <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">No background tasks yet.</CardContent></Card> : tasks.map((task) => <Link key={task.id} href={`/tasks/${task.id}`}><Card className="transition-colors hover:bg-muted/40"><CardContent className="flex items-center justify-between gap-4"><div className="min-w-0"><p className="truncate font-medium">{task.title}</p><p className="text-xs text-muted-foreground">{task.coworker_name} · {new Date(task.created_at).toLocaleString()}</p></div><Badge variant={task.status === "failed" || task.status === "blocked" ? "destructive" : "outline"}><ClockIcon className="mr-1 size-3" />{STATUS_LABEL[task.status]}</Badge></CardContent></Card></Link>)}
      </div>
    </div>
  );
}
