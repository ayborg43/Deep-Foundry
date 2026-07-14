"use client";

import { FormEvent, useEffect, useState } from "react";
import { BotIcon, PlayIcon, PlusIcon, UsersIcon } from "lucide-react";
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
import type { AgentTeam, Coworker } from "@/lib/types";

export default function AgentTeamsPage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState("");
  const [teams, setTeams] = useState<AgentTeam[]>([]);
  const [coworkers, setCoworkers] = useState<Coworker[]>([]);
  const [name, setName] = useState("");
  const [managerId, setManagerId] = useState("");
  const [workerId, setWorkerId] = useState("");
  const [objectives, setObjectives] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load(id: string) {
    const [teamRows, coworkerRows] = await Promise.all([
      apiFetch<AgentTeam[]>(`/agent-teams?workspace_id=${id}`),
      apiFetch<Coworker[]>(`/workspaces/${id}/coworkers`),
    ]);
    setTeams(teamRows); setCoworkers(coworkerRows);
    setManagerId((value) => value || coworkerRows[0]?.id || "");
    setWorkerId((value) => value || coworkerRows[1]?.id || coworkerRows[0]?.id || "");
  }

  useEffect(() => {
    if (!getTokens()) { router.push("/login"); return; }
    void getWorkspaceId().then((id) => {
      if (!id) return;
      setWorkspaceId(id);
      load(id).catch(() => setError("Couldn’t load agent teams."));
    });
  }, [router]);

  async function createTeam(event: FormEvent) {
    event.preventDefault(); if (!workspaceId || !name.trim() || !managerId || !workerId) return;
    setBusy(true); setError(null);
    try {
      await apiFetch("/agent-teams", { method: "POST", body: JSON.stringify({
        workspace_id: workspaceId, name, collaboration_pattern: "manager_delegate",
        members: [
          { coworker_id: managerId, role: "manager" },
          ...(workerId === managerId ? [] : [{ coworker_id: workerId, role: "custom", custom_role_label: "Specialist" }]),
        ],
      }) });
      setName(""); await load(workspaceId);
    } catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn’t create the team."); }
    finally { setBusy(false); }
  }

  async function runTeam(team: AgentTeam) {
    const objective = objectives[team.id]?.trim(); if (!objective) return;
    setBusy(true); setError(null);
    try {
      const run = await apiFetch<{ id: string }>(`/agent-teams/${team.id}/run`, { method: "POST", body: JSON.stringify({ objective }) });
      setObjectives((current) => ({ ...current, [team.id]: "" }));
      window.alert(`Team run ${run.id} is queued. You can follow its delegated tasks from Tasks.`);
    } catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn’t start the team."); }
    finally { setBusy(false); }
  }

  return <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-10">
    <header><h1 className="flex items-center gap-2 text-2xl font-semibold"><UsersIcon className="size-6" />Agent teams</h1><p className="text-sm text-muted-foreground">A manager plans the objective, delegates work, and synthesizes one final result.</p></header>
    {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
    <Card><CardHeader><CardTitle>Create a manager/delegate team</CardTitle></CardHeader><CardContent>
      <form onSubmit={createTeam} className="grid gap-4 sm:grid-cols-3">
        <div className="grid gap-1.5"><Label htmlFor="team-name">Team name</Label><Input id="team-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Launch team" /></div>
        <div className="grid gap-1.5"><Label htmlFor="manager">Manager</Label><Select value={managerId} onValueChange={setManagerId}><SelectTrigger id="manager"><SelectValue placeholder="Choose manager" /></SelectTrigger><SelectContent>{coworkers.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent></Select></div>
        <div className="grid gap-1.5"><Label htmlFor="worker">Specialist</Label><Select value={workerId} onValueChange={setWorkerId}><SelectTrigger id="worker"><SelectValue placeholder="Choose specialist" /></SelectTrigger><SelectContent>{coworkers.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent></Select></div>
        <Button disabled={busy || !name.trim() || !managerId || !workerId} className="w-fit"><PlusIcon data-icon="inline-start" />Create team</Button>
      </form>
    </CardContent></Card>
    <section className="grid gap-4 md:grid-cols-2" aria-label="Agent teams">
      {teams.length === 0 ? <Card className="md:col-span-2"><CardContent className="py-10 text-center text-sm text-muted-foreground">No agent teams yet. Create two coworkers first, then combine them here.</CardContent></Card> : teams.map((team) => <Card key={team.id}>
        <CardHeader><div className="flex items-start justify-between gap-3"><CardTitle className="flex items-center gap-2"><BotIcon className="size-4" />{team.name}</CardTitle><Badge variant="outline">v{team.version}</Badge></div></CardHeader>
        <CardContent className="grid gap-4"><div className="flex flex-wrap gap-2">{team.members.map((m) => <Badge key={m.id} variant={m.role === "manager" ? "default" : "secondary"}>{m.coworker_name} · {m.role}</Badge>)}</div>
          <div className="grid gap-1.5"><Label htmlFor={`objective-${team.id}`}>Run objective</Label><Textarea id={`objective-${team.id}`} value={objectives[team.id] || ""} onChange={(e) => setObjectives((current) => ({ ...current, [team.id]: e.target.value }))} placeholder="Prepare a launch plan and review it for risks." /></div>
          <Button onClick={() => runTeam(team)} disabled={busy || !objectives[team.id]?.trim()} className="w-fit"><PlayIcon data-icon="inline-start" />Run team</Button>
        </CardContent></Card>)}
    </section>
  </main>;
}
