"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { SearchIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import type { AuditLogEntry, AuditLogPage, Coworker } from "@/lib/types";

export default function AuditPage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [items, setItems] = useState<AuditLogEntry[]>([]);
  const [coworkers, setCoworkers] = useState<Coworker[]>([]);
  const [action, setAction] = useState("");
  const [coworkerId, setCoworkerId] = useState("");
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load(workspace: string, offset = 0, append = false) {
    const params = new URLSearchParams({ limit: "50", offset: String(offset) });
    if (action.trim()) params.set("action", action.trim());
    if (coworkerId) params.set("coworker_id", coworkerId);
    const page = await apiFetch<AuditLogPage>(`/workspaces/${workspace}/audit-log?${params}`);
    setItems((current) => append ? [...current, ...page.results] : page.results);
    setNextOffset(page.next_offset);
  }

  useEffect(() => {
    if (!getTokens()) { router.push("/login"); return; }
    const timer = window.setTimeout(() => {
      void (async () => {
        const workspace = await getWorkspaceId(); setWorkspaceId(workspace); if (!workspace) return;
        try { const coworkerData = await apiFetch<Coworker[]>(`/workspaces/${workspace}/coworkers`); setCoworkers(coworkerData); await load(workspace); }
        catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn't load audit log."); }
      })();
    }, 0);
    return () => window.clearTimeout(timer);
    // Initial load intentionally excludes mutable filter state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-12">
      <div><h1 className="text-xl font-semibold">Audit log</h1><p className="text-sm text-muted-foreground">An immutable, attributable record of workspace and coworker activity.</p></div>
      {error ? <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert> : null}
      <Card><CardContent className="flex flex-wrap gap-2"><Input className="min-w-48 flex-1" value={action} onChange={(event) => setAction(event.target.value)} placeholder="Filter actions, e.g. tool or model" /><select className="h-8 rounded-lg border bg-background px-2 text-sm" value={coworkerId} onChange={(event) => setCoworkerId(event.target.value)} aria-label="Filter by coworker"><option value="">All coworkers</option>{coworkers.map((coworker) => <option key={coworker.id} value={coworker.id}>{coworker.name}</option>)}</select><Button disabled={!workspaceId} onClick={() => workspaceId && void load(workspaceId)}><SearchIcon data-icon="inline-start" />Filter</Button></CardContent></Card>
      <div className="flex flex-col gap-2">{items.length === 0 ? <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">No matching audit events.</CardContent></Card> : items.map((item) => <details key={item.id} className="rounded-lg border bg-card px-4 py-3"><summary className="flex cursor-pointer list-none items-center gap-3"><Badge variant="outline">{item.actor_type}</Badge><div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{item.action}</p><p className="text-xs text-muted-foreground">{item.actor_label ?? item.actor_id ?? "Unknown actor"} · {item.resource_type}{item.resource_id ? ` · ${item.resource_id}` : ""}</p></div><time className="shrink-0 text-xs text-muted-foreground">{new Date(item.created_at).toLocaleString()}</time></summary><pre className="mt-3 overflow-x-auto border-t pt-3 text-xs text-muted-foreground">{JSON.stringify(item.metadata, null, 2)}</pre></details>)}</div>
      {nextOffset !== null && workspaceId ? <Button variant="outline" className="self-center" onClick={() => void load(workspaceId, nextOffset, true)}>Load more</Button> : null}
    </div>
  );
}
