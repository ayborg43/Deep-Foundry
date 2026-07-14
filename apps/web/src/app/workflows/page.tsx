"use client";

import { FormEvent, useEffect, useState } from "react";
import { CalendarClockIcon, CheckIcon, GitBranchIcon, PlayIcon, PlusIcon, XIcon } from "lucide-react";
import { useRouter } from "next/navigation";

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
import type { Coworker, Workflow, WorkflowRun } from "@/lib/types";

export default function WorkflowsPage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState("");
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [coworkers, setCoworkers] = useState<Coworker[]>([]);
  const [runs, setRuns] = useState<Record<string, WorkflowRun[]>>({});
  const [name, setName] = useState(""); const [instructions, setInstructions] = useState("");
  const [useCondition, setUseCondition] = useState(false); const [conditionPath, setConditionPath] = useState("priority"); const [conditionValue, setConditionValue] = useState("high");
  const [coworkerId, setCoworkerId] = useState(""); const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);

  async function load(id: string) {
    const [workflowRows, coworkerRows] = await Promise.all([apiFetch<Workflow[]>(`/workflows?workspace_id=${id}`), apiFetch<Coworker[]>(`/workspaces/${id}/coworkers`)]);
    setWorkflows(workflowRows); setCoworkers(coworkerRows); setCoworkerId((v) => v || coworkerRows[0]?.id || "");
    const histories = await Promise.all(workflowRows.map(async (w) => [w.id, await apiFetch<WorkflowRun[]>(`/workflows/${w.id}/runs`)] as const));
    setRuns(Object.fromEntries(histories));
  }

  useEffect(() => { if (!getTokens()) { router.push("/login"); return; } void getWorkspaceId().then((id) => { if (id) { setWorkspaceId(id); load(id).catch(() => setError("Couldn’t load workflows.")); } }); }, [router]);

  async function createWorkflow(event: FormEvent) {
    event.preventDefault(); if (!name.trim() || !instructions.trim() || !coworkerId) return; setBusy(true); setError(null);
    const action = { type: "coworker_action", title: "Prepare work", coworker_id: coworkerId, instructions };
    const checkpoint = { type: "human_checkpoint", title: "Review and approve" };
    const steps = useCondition ? [{ type: "condition", title: "Evaluate run context", condition: { path: conditionPath, operator: "equals", value: conditionValue }, if_true: 1, if_false: 2 }, action, checkpoint] : [action, checkpoint];
    try { await apiFetch("/workflows", { method: "POST", body: JSON.stringify({ workspace_id: workspaceId, name, definition: { steps } }) }); setName(""); setInstructions(""); await load(workspaceId); }
    catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn’t create workflow."); } finally { setBusy(false); }
  }

  async function runWorkflow(workflow: Workflow) { setBusy(true); try { await apiFetch(`/workflows/${workflow.id}/runs`, { method: "POST", body: "{}" }); await load(workspaceId); } catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn’t run workflow."); } finally { setBusy(false); } }
  async function schedule(workflow: Workflow) { setBusy(true); try { await apiFetch(`/workflows/${workflow.id}/triggers`, { method: "POST", body: JSON.stringify({ trigger_type: "scheduled", schedule_cron: "0 9 * * 1", enabled: true }) }); await load(workspaceId); } catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn’t schedule workflow."); } finally { setBusy(false); } }
  async function decide(run: WorkflowRun, stepId: string, action: "approve" | "deny") { setBusy(true); try { await apiFetch(`/workflow-runs/${run.id}/steps/${stepId}/${action}`, { method: "POST", body: "{}" }); await load(workspaceId); } catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn’t update checkpoint."); } finally { setBusy(false); } }

  return <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-10">
    <header><h1 className="flex items-center gap-2 text-2xl font-semibold"><GitBranchIcon className="size-6" />Workflows</h1><p className="text-sm text-muted-foreground">Build durable scheduled work with explicit human checkpoints and complete run history.</p></header>
    {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
    <Card><CardHeader><CardTitle>New reviewed workflow</CardTitle></CardHeader><CardContent><form onSubmit={createWorkflow} className="grid gap-4 sm:grid-cols-2">
      <div className="grid gap-1.5"><Label htmlFor="workflow-name">Name</Label><Input id="workflow-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Weekly client report" /></div>
      <div className="grid gap-1.5"><Label htmlFor="workflow-coworker">Coworker</Label><Select value={coworkerId} onValueChange={setCoworkerId}><SelectTrigger id="workflow-coworker"><SelectValue placeholder="Choose coworker" /></SelectTrigger><SelectContent>{coworkers.map((c) => <SelectItem value={c.id} key={c.id}>{c.name}</SelectItem>)}</SelectContent></Select></div>
      <div className="grid gap-1.5 sm:col-span-2"><Label htmlFor="workflow-instructions">Instructions</Label><Textarea id="workflow-instructions" value={instructions} onChange={(e) => setInstructions(e.target.value)} placeholder="Compile the week’s activity into a concise client-ready report." /></div>
      <div className="grid gap-3 rounded-md border p-3 sm:col-span-2"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="font-medium">Conditional branch</p><p className="text-xs text-muted-foreground">Run the coworker step only when workflow context matches; otherwise move directly to approval.</p></div><Button type="button" variant={useCondition ? "default" : "outline"} aria-pressed={useCondition} onClick={() => setUseCondition((value) => !value)}>{useCondition ? "Enabled" : "Add condition"}</Button></div>{useCondition && <div className="grid gap-3 sm:grid-cols-2"><div className="grid gap-1.5"><Label htmlFor="condition-path">Context field</Label><Input id="condition-path" value={conditionPath} onChange={(e) => setConditionPath(e.target.value)} /></div><div className="grid gap-1.5"><Label htmlFor="condition-value">Equals</Label><Input id="condition-value" value={conditionValue} onChange={(e) => setConditionValue(e.target.value)} /></div></div>}</div>
      <Button className="w-fit" disabled={busy || !name.trim() || !instructions.trim() || !coworkerId}><PlusIcon data-icon="inline-start" />Create workflow</Button>
    </form></CardContent></Card>
    <section className="grid gap-4" aria-label="Workflows">{workflows.length === 0 ? <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">No workflows yet.</CardContent></Card> : workflows.map((workflow) => <Card key={workflow.id}><CardHeader><div className="flex flex-wrap items-start justify-between gap-3"><div><CardTitle>{workflow.name}</CardTitle><p className="mt-1 text-xs text-muted-foreground">{workflow.definition.steps.length} steps · version {workflow.version}</p></div><div className="flex gap-2"><Button variant="outline" size="sm" onClick={() => schedule(workflow)} disabled={busy || workflow.triggers.some((t) => t.trigger_type === "scheduled")}><CalendarClockIcon data-icon="inline-start" />{workflow.triggers.some((t) => t.trigger_type === "scheduled") ? "Scheduled" : "Every Monday"}</Button><Button size="sm" onClick={() => runWorkflow(workflow)} disabled={busy}><PlayIcon data-icon="inline-start" />Run now</Button></div></div></CardHeader>
      <CardContent className="grid gap-3">{(runs[workflow.id] || []).slice(0, 3).map((run) => { const checkpoint = run.steps.find((s) => s.status === "needs_approval"); return <div key={run.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3"><div><p className="text-sm font-medium">Run {run.id.slice(0, 8)}</p><p className="text-xs text-muted-foreground">Started {new Date(run.started_at).toLocaleString()}</p></div><div className="flex items-center gap-2"><Badge variant={run.status === "failed" ? "destructive" : "outline"}>{run.status.replace("_", " ")}</Badge>{checkpoint?.id && <><Button size="sm" onClick={() => decide(run, checkpoint.id!, "approve")}><CheckIcon data-icon="inline-start" />Approve</Button><Button size="sm" variant="destructive" onClick={() => decide(run, checkpoint.id!, "deny")}><XIcon data-icon="inline-start" />Deny</Button></>}</div></div>; })}</CardContent></Card>)}</section>
  </main>;
}
