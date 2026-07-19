"use client";

import { FormEvent, useEffect, useState } from "react";
import { BotIcon, PlayIcon, PlusIcon, Trash2Icon, UsersIcon } from "lucide-react";
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
import type { AgentTeam, AgentTeamMember, Coworker } from "@/lib/types";

type MemberRole = AgentTeamMember["role"];
type MemberDraft = { coworkerId: string; role: MemberRole; customLabel: string };

const ROLE_OPTIONS: { value: MemberRole; label: string }[] = [
  { value: "manager", label: "Manager" },
  { value: "researcher", label: "Researcher" },
  { value: "writer", label: "Writer" },
  { value: "reviewer", label: "Reviewer" },
  { value: "developer", label: "Developer" },
  { value: "tester", label: "Tester" },
  { value: "security_reviewer", label: "Security reviewer" },
  { value: "architect", label: "Architect" },
  { value: "planner", label: "Planner" },
  { value: "product_manager", label: "Product manager" },
  { value: "custom", label: "Custom..." },
];

const PATTERNS: { value: AgentTeam["collaboration_pattern"]; label: string; hint: string }[] = [
  { value: "manager_delegate", label: "Manager / delegate", hint: "The manager plans, everyone else contributes in parallel, the manager synthesizes one final result." },
  { value: "sequential", label: "Sequential", hint: "A relay in the order listed below — each member continues from the previous member's result." },
  { value: "parallel_merge", label: "Parallel / merge", hint: "Everyone works the objective at once; the results are merged." },
];

export default function AgentTeamsPage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState("");
  const [teams, setTeams] = useState<AgentTeam[]>([]);
  const [coworkers, setCoworkers] = useState<Coworker[]>([]);
  const [name, setName] = useState("");
  const [pattern, setPattern] = useState<AgentTeam["collaboration_pattern"]>("manager_delegate");
  const [members, setMembers] = useState<MemberDraft[]>([]);
  const [objectives, setObjectives] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load(id: string) {
    const [teamRows, coworkerRows] = await Promise.all([
      apiFetch<AgentTeam[]>(`/agent-teams?workspace_id=${id}`),
      apiFetch<Coworker[]>(`/workspaces/${id}/coworkers`),
    ]);
    setTeams(teamRows); setCoworkers(coworkerRows);
    setMembers((current) =>
      current.length > 0
        ? current
        : [
            { coworkerId: coworkerRows[0]?.id || "", role: "manager", customLabel: "" },
            { coworkerId: coworkerRows[1]?.id || "", role: "researcher", customLabel: "" },
          ]
    );
  }

  useEffect(() => {
    if (!getTokens()) { router.push("/login"); return; }
    void getWorkspaceId().then((id) => {
      if (!id) return;
      setWorkspaceId(id);
      load(id).catch(() => setError("Couldn’t load agent teams."));
    });
  }, [router]);

  function updateMember(index: number, patch: Partial<MemberDraft>) {
    setMembers((current) => current.map((member, i) => (i === index ? { ...member, ...patch } : member)));
  }

  const filledMembers = members.filter((member) => member.coworkerId);
  const managerCount = filledMembers.filter((member) => member.role === "manager").length;
  const memberProblem =
    filledMembers.length === 0
      ? "Add at least one coworker."
      : new Set(filledMembers.map((member) => member.coworkerId)).size !== filledMembers.length
        ? "Each coworker can only appear once."
        : pattern === "manager_delegate" && managerCount !== 1
          ? "Manager/delegate teams need exactly one member with the Manager role."
          : null;

  async function createTeam(event: FormEvent) {
    event.preventDefault();
    if (!workspaceId || !name.trim() || memberProblem) return;
    setBusy(true); setError(null);
    try {
      await apiFetch("/agent-teams", { method: "POST", body: JSON.stringify({
        workspace_id: workspaceId, name, collaboration_pattern: pattern,
        members: filledMembers.map((member) => ({
          coworker_id: member.coworkerId,
          role: member.role,
          ...(member.role === "custom" ? { custom_role_label: member.customLabel || "Specialist" } : {}),
        })),
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
    <Card><CardHeader><CardTitle>Create a team</CardTitle></CardHeader><CardContent>
      <form onSubmit={createTeam} className="grid gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="grid gap-1.5"><Label htmlFor="team-name">Team name</Label><Input id="team-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Launch team" /></div>
          <div className="grid gap-1.5">
            <Label htmlFor="team-pattern">Collaboration pattern</Label>
            <Select value={pattern} onValueChange={(value) => setPattern(value as AgentTeam["collaboration_pattern"])}>
              <SelectTrigger id="team-pattern"><SelectValue /></SelectTrigger>
              <SelectContent>{PATTERNS.map((p) => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}</SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">{PATTERNS.find((p) => p.value === pattern)?.hint}</p>
          </div>
        </div>

        <div className="grid gap-2">
          <Label>Members{pattern === "sequential" ? " (runs in this order)" : ""}</Label>
          {members.map((member, index) => (
            <div key={index} className="grid gap-2 rounded-md border p-3 sm:grid-cols-[1fr_1fr_auto]">
              <div className="grid gap-1.5">
                <Label htmlFor={`member-coworker-${index}`} className="text-xs text-muted-foreground">Coworker</Label>
                <Select value={member.coworkerId} onValueChange={(value) => updateMember(index, { coworkerId: value })}>
                  <SelectTrigger id={`member-coworker-${index}`}><SelectValue placeholder="Choose coworker" /></SelectTrigger>
                  <SelectContent>{coworkers.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor={`member-role-${index}`} className="text-xs text-muted-foreground">What they do</Label>
                <Select value={member.role} onValueChange={(value) => updateMember(index, { role: value as MemberRole })}>
                  <SelectTrigger id={`member-role-${index}`}><SelectValue /></SelectTrigger>
                  <SelectContent>{ROLE_OPTIONS.map((role) => <SelectItem key={role.value} value={role.value}>{role.label}</SelectItem>)}</SelectContent>
                </Select>
                {member.role === "custom" && (
                  <Input
                    aria-label="Custom role description"
                    value={member.customLabel}
                    onChange={(e) => updateMember(index, { customLabel: e.target.value })}
                    placeholder="e.g. Data analyst — pulls the numbers"
                  />
                )}
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="self-end text-muted-foreground hover:text-destructive"
                aria-label={`Remove member ${index + 1}`}
                disabled={members.length <= 1}
                onClick={() => setMembers((current) => current.filter((_, i) => i !== index))}
              >
                <Trash2Icon />
              </Button>
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="w-fit"
            onClick={() => setMembers((current) => [...current, { coworkerId: "", role: "researcher", customLabel: "" }])}
          >
            <PlusIcon data-icon="inline-start" />Add member
          </Button>
          {memberProblem && <p className="text-xs text-destructive">{memberProblem}</p>}
        </div>

        <Button disabled={busy || !name.trim() || Boolean(memberProblem)} className="w-fit"><PlusIcon data-icon="inline-start" />Create team</Button>
      </form>
    </CardContent></Card>
    <section className="grid gap-4 md:grid-cols-2" aria-label="Agent teams">
      {teams.length === 0 ? <Card className="md:col-span-2"><CardContent className="py-10 text-center text-sm text-muted-foreground">No agent teams yet. Create two coworkers first, then combine them here.</CardContent></Card> : teams.map((team) => <Card key={team.id}>
        <CardHeader><div className="flex items-start justify-between gap-3"><CardTitle className="flex items-center gap-2"><BotIcon className="size-4" />{team.name}</CardTitle><Badge variant="outline">v{team.version}</Badge></div></CardHeader>
        <CardContent className="grid gap-4"><div className="flex flex-wrap gap-2">{team.members.map((m) => <Badge key={m.id} variant={m.role === "manager" ? "default" : "secondary"}>{m.coworker_name} · {m.role === "custom" && m.custom_role_label ? m.custom_role_label : m.role.replace(/_/g, " ")}</Badge>)}</div>
          <div className="grid gap-1.5"><Label htmlFor={`objective-${team.id}`}>Run objective</Label><Textarea id={`objective-${team.id}`} value={objectives[team.id] || ""} onChange={(e) => setObjectives((current) => ({ ...current, [team.id]: e.target.value }))} placeholder="Prepare a launch plan and review it for risks." /></div>
          <Button onClick={() => runTeam(team)} disabled={busy || !objectives[team.id]?.trim()} className="w-fit"><PlayIcon data-icon="inline-start" />Run team</Button>
        </CardContent></Card>)}
    </section>
  </main>;
}
