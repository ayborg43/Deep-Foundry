"use client";

import { FormEvent, useEffect, useState } from "react";
import { FileOutputIcon, PlusIcon } from "lucide-react";
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
import type { Artifact } from "@/lib/types";

export default function ArtifactsPage() {
  const router = useRouter(); const [workspaceId, setWorkspaceId] = useState(""); const [rows, setRows] = useState<Artifact[]>([]); const [name, setName] = useState(""); const [type, setType] = useState<Artifact["artifact_type"]>("presentation"); const [source, setSource] = useState(""); const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  async function load(id: string) { setRows(await apiFetch<Artifact[]>(`/artifacts?workspace_id=${id}`)); }
  useEffect(() => { if (!getTokens()) { router.push("/login"); return; } void getWorkspaceId().then((id) => { if (id) { setWorkspaceId(id); load(id).catch(() => setError("Couldn’t load artifacts.")); } }); }, [router]);
  async function create(event: FormEvent) { event.preventDefault(); setBusy(true); try { await apiFetch("/artifacts", { method: "POST", body: JSON.stringify({ workspace_id: workspaceId, artifact_type: type, name, content: type === "diagram" ? { mermaid: source } : type === "presentation" ? { outline: source.split("\n").filter(Boolean) } : { analysis: source } }) }); setName(""); setSource(""); await load(workspaceId); } catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn’t create artifact."); } finally { setBusy(false); } }
  return <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-10"><header><h1 className="flex items-center gap-2 text-2xl font-semibold"><FileOutputIcon className="size-6" />Artifacts</h1><p className="text-sm text-muted-foreground">Keep presentations, diagrams, video analyses, portable coworkers, and compliance evidence as integrity-checked workspace artifacts.</p></header>{error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}<Card><CardHeader><CardTitle>New structured artifact</CardTitle></CardHeader><CardContent><form onSubmit={create} className="grid gap-4 sm:grid-cols-2"><div className="grid gap-1.5"><Label htmlFor="artifact-name">Name</Label><Input id="artifact-name" value={name} onChange={(e) => setName(e.target.value)} required /></div><div className="grid gap-1.5"><Label htmlFor="artifact-type">Type</Label><Select value={type} onValueChange={(value) => setType(value as Artifact["artifact_type"])}><SelectTrigger id="artifact-type"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="presentation">Presentation outline</SelectItem><SelectItem value="diagram">Diagram</SelectItem><SelectItem value="video_analysis">Video analysis</SelectItem></SelectContent></Select></div><div className="grid gap-1.5 sm:col-span-2"><Label htmlFor="artifact-source">Structured content</Label><Textarea id="artifact-source" rows={6} value={source} onChange={(e) => setSource(e.target.value)} placeholder={type === "diagram" ? "graph TD; A-->B" : "Add one point per line."} required /></div><Button className="w-fit" disabled={busy || !name.trim() || !source.trim()}><PlusIcon data-icon="inline-start" />Create artifact</Button></form></CardContent></Card><section className="grid gap-4 sm:grid-cols-2">{rows.map((row) => <Card key={row.id}><CardHeader><div className="flex items-start justify-between gap-3"><CardTitle className="text-base">{row.name}</CardTitle><Badge variant="outline">{row.artifact_type.replace("_", " ")}</Badge></div></CardHeader><CardContent><pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 text-xs">{JSON.stringify(row.content, null, 2)}</pre><p className="mt-2 break-all text-xs text-muted-foreground">SHA-256 {row.checksum}</p></CardContent></Card>)}</section></main>;
}
