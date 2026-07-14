"use client";

import { FormEvent, useEffect, useState } from "react";
import { PlusIcon, ShieldCheckIcon, UsersIcon } from "lucide-react";
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

type Member = { id: string; email: string; role: string };
type Floor = { id: string; risk: string; min_required_policy: string; enforced: boolean };

export default function OrganizationSettingsPage() {
  const router = useRouter(); const [workspaceId, setWorkspaceId] = useState(""); const [members, setMembers] = useState<Member[]>([]); const [floors, setFloors] = useState<Floor[]>([]);
  const [email, setEmail] = useState(""); const [role, setRole] = useState("member"); const [bundle, setBundle] = useState(""); const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  async function load(id: string) { const [m, f] = await Promise.all([apiFetch<Member[]>(`/workspaces/${id}/members`), apiFetch<Floor[]>(`/workspaces/${id}/policy-floors`)]); setMembers(m); setFloors(f); }
  useEffect(() => { if (!getTokens()) { router.push("/login"); return; } void getWorkspaceId().then((id) => { if (id) { setWorkspaceId(id); load(id).catch(() => setError("Couldn’t load organization settings.")); } }); }, [router]);
  async function invite(event: FormEvent) { event.preventDefault(); setBusy(true); try { await apiFetch(`/workspaces/${workspaceId}/members`, { method: "POST", body: JSON.stringify({ email, role }) }); setEmail(""); await load(workspaceId); } catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn’t add member."); } finally { setBusy(false); } }
  async function enforce(risk: "safe" | "sensitive" | "dangerous") { setBusy(true); try { await apiFetch(`/workspaces/${workspaceId}/policy-floors`, { method: "POST", body: JSON.stringify({ tool_risk_classification: risk, enforced: true }) }); await load(workspaceId); } catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn’t update policy floor."); } finally { setBusy(false); } }
  async function importBundle() { setBusy(true); setError(null); try { await apiFetch(`/workspaces/${workspaceId}/coworkers/import`, { method: "POST", body: JSON.stringify({ bundle: JSON.parse(bundle) }) }); setBundle(""); } catch (err) { setError(err instanceof ApiRequestError ? err.message : err instanceof SyntaxError ? "The coworker bundle is not valid JSON." : "Couldn’t import coworker."); } finally { setBusy(false); } }
  return <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-4 py-10"><header><h1 className="flex items-center gap-2 text-2xl font-semibold"><UsersIcon className="size-6" />Organization</h1><p className="text-sm text-muted-foreground">Manage delegated roles, policy floors, and portable coworkers.</p></header>{error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
    <Card><CardHeader><CardTitle>Add member</CardTitle></CardHeader><CardContent><form onSubmit={invite} className="flex flex-col gap-3 sm:flex-row sm:items-end"><div className="grid flex-1 gap-1.5"><Label htmlFor="member-email">Email</Label><Input id="member-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></div><div className="grid gap-1.5"><Label htmlFor="member-role">Role</Label><Select value={role} onValueChange={setRole}><SelectTrigger id="member-role" className="w-48"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="admin">Admin</SelectItem><SelectItem value="security_admin">Security admin</SelectItem><SelectItem value="billing_admin">Billing admin</SelectItem><SelectItem value="developer_admin">Developer admin</SelectItem><SelectItem value="auditor">Auditor</SelectItem><SelectItem value="member">Member</SelectItem><SelectItem value="guest">Guest</SelectItem></SelectContent></Select></div><Button disabled={busy}><PlusIcon data-icon="inline-start" />Add</Button></form></CardContent></Card>
    <Card><CardHeader><CardTitle>Members</CardTitle></CardHeader><CardContent className="grid gap-2">{members.map((m) => <div key={m.id} className="flex items-center justify-between rounded-md border p-3"><span className="text-sm">{m.email}</span><Badge variant="outline">{m.role.replace("_", " ")}</Badge></div>)}</CardContent></Card>
    <Card><CardHeader><CardTitle className="flex items-center gap-2"><ShieldCheckIcon className="size-4" />Policy floors</CardTitle></CardHeader><CardContent className="grid gap-3 sm:grid-cols-3">{(["safe", "sensitive", "dangerous"] as const).map((risk) => { const active = floors.some((f) => f.risk === risk && f.enforced); return <div key={risk} className="grid gap-3 rounded-md border p-3"><div><p className="font-medium capitalize">{risk} tools</p><p className="text-xs text-muted-foreground">Minimum: {active ? "approval" : "coworker policy"}</p></div><Button variant={active ? "secondary" : "outline"} disabled={active || busy} onClick={() => enforce(risk)}>{active ? "Enforced" : "Require approval"}</Button></div>; })}</CardContent></Card>
    <Card><CardHeader><CardTitle>Import portable coworker</CardTitle></CardHeader><CardContent className="grid gap-3"><div className="grid gap-1.5"><Label htmlFor="coworker-bundle">Coworker bundle JSON</Label><Textarea id="coworker-bundle" rows={6} value={bundle} onChange={(e) => setBundle(e.target.value)} /><p className="text-xs text-muted-foreground">Bundles contain configuration, skills, and tool names. Private memory and credentials are never included.</p></div><Button className="w-fit" disabled={busy || !bundle.trim()} onClick={importBundle}>Import coworker</Button></CardContent></Card>
  </main>;
}
