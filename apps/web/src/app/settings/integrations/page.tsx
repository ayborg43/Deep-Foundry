"use client";

import { FormEvent, useEffect, useState } from "react";
import { CableIcon, CopyIcon, PlusIcon } from "lucide-react";
import { useRouter } from "next/navigation";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import type { Integration } from "@/lib/types";

const kinds: Integration["kind"][] = ["email", "calendar", "slack", "discord", "github", "webhook"];

export default function IntegrationsPage() {
  const router = useRouter(); const [workspaceId, setWorkspaceId] = useState(""); const [rows, setRows] = useState<Integration[]>([]);
  const [kind, setKind] = useState<Integration["kind"]>("webhook"); const [name, setName] = useState(""); const [endpoint, setEndpoint] = useState("");
  const [revealedSecret, setRevealedSecret] = useState(""); const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  async function load(id: string) { setRows(await apiFetch<Integration[]>(`/integrations?workspace_id=${id}`)); }
  useEffect(() => { if (!getTokens()) { router.push("/login"); return; } void getWorkspaceId().then((id) => { if (id) { setWorkspaceId(id); load(id).catch(() => setError("Couldn’t load integrations.")); } }); }, [router]);
  async function create(event: FormEvent) { event.preventDefault(); setBusy(true); setError(null); try { const result = await apiFetch<{ signing_secret: string }>("/integrations", { method: "POST", body: JSON.stringify({ workspace_id: workspaceId, kind, name: name || kind, config: endpoint ? { endpoint_url: endpoint } : {} }) }); setRevealedSecret(result.signing_secret); setName(""); setEndpoint(""); await load(workspaceId); } catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn’t create integration."); } finally { setBusy(false); } }
  return <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-4 py-10"><header><h1 className="flex items-center gap-2 text-2xl font-semibold"><CableIcon className="size-6" />Integrations</h1><p className="text-sm text-muted-foreground">Connect events from email, calendars, chat, GitHub, or signed webhooks to workflows.</p></header>{error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
    {revealedSecret && <Alert><AlertDescription><strong>Copy this signing secret now:</strong> <code className="break-all">{revealedSecret}</code> <Button variant="ghost" size="sm" onClick={() => navigator.clipboard.writeText(revealedSecret)}><CopyIcon data-icon="inline-start" />Copy</Button></AlertDescription></Alert>}
    <Card><CardHeader><CardTitle>Connect a service</CardTitle></CardHeader><CardContent><form onSubmit={create} className="grid gap-4 sm:grid-cols-2"><div className="grid gap-1.5"><Label htmlFor="integration-kind">Service</Label><Select value={kind} onValueChange={(value) => setKind(value as Integration["kind"])}><SelectTrigger id="integration-kind"><SelectValue /></SelectTrigger><SelectContent>{kinds.map((item) => <SelectItem key={item} value={item}>{item[0].toUpperCase() + item.slice(1)}</SelectItem>)}</SelectContent></Select></div><div className="grid gap-1.5"><Label htmlFor="integration-name">Display name</Label><Input id="integration-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Production GitHub" /></div><div className="grid gap-1.5 sm:col-span-2"><Label htmlFor="integration-endpoint">Endpoint URL (optional)</Label><Input id="integration-endpoint" type="url" value={endpoint} onChange={(e) => setEndpoint(e.target.value)} placeholder="https://hooks.example.com/..." /></div><Button className="w-fit" disabled={busy || !workspaceId}><PlusIcon data-icon="inline-start" />Connect</Button></form></CardContent></Card>
    <Card><CardHeader><CardTitle>Connected services</CardTitle></CardHeader><CardContent className="grid gap-3">{rows.length === 0 ? <p className="py-6 text-center text-sm text-muted-foreground">No integrations connected.</p> : rows.map((row) => <div key={row.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3"><div><p className="font-medium">{row.name}</p><p className="text-xs text-muted-foreground">Webhook token: {row.workspace_token}</p></div><Badge variant={row.enabled ? "default" : "secondary"}>{row.kind}</Badge></div>)}</CardContent></Card>
  </main>;
}
