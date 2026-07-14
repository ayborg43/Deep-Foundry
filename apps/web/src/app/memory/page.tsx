"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BrainIcon, PencilIcon, PlusIcon, Trash2Icon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import type { Coworker, MemoryEntry } from "@/lib/types";

export default function MemoryPage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [coworkers, setCoworkers] = useState<Coworker[]>([]);
  const [coworkerId, setCoworkerId] = useState("");
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [content, setContent] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadTimeline(id: string) {
    setEntries(await apiFetch<MemoryEntry[]>(`/memory/coworker/${id}/timeline`));
  }

  useEffect(() => {
    if (!getTokens()) { router.push("/login"); return; }
    void (async () => {
      const workspace = await getWorkspaceId();
      setWorkspaceId(workspace);
      if (!workspace) return;
      try {
        const data = await apiFetch<Coworker[]>(`/workspaces/${workspace}/coworkers`);
        setCoworkers(data);
        if (data[0]) { setCoworkerId(data[0].id); await loadTimeline(data[0].id); }
      } catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn't load memory."); }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function save() {
    if (!workspaceId || !coworkerId || !content.trim()) return;
    setBusy(true); setError(null);
    try {
      if (editingId) {
        await apiFetch(`/memory/${editingId}`, { method: "PATCH", body: JSON.stringify({ content }) });
      } else {
        await apiFetch("/memory", { method: "POST", body: JSON.stringify({ workspace_id: workspaceId, scope: "coworker", scope_id: coworkerId, content }) });
      }
      setContent(""); setEditingId(null); await loadTimeline(coworkerId);
    } catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn't save memory."); }
    finally { setBusy(false); }
  }

  async function remove(id: string) {
    try { await apiFetch(`/memory/${id}`, { method: "DELETE" }); setEntries((current) => current.filter((entry) => entry.id !== id)); }
    catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn't delete memory."); }
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-4 py-12">
      <div><h1 className="text-xl font-semibold">Memory</h1><p className="text-sm text-muted-foreground">See and control what each coworker remembers across conversations.</p></div>
      {error ? <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert> : null}
      <Select value={coworkerId} onValueChange={(id) => { setCoworkerId(id); void loadTimeline(id); }}>
        <SelectTrigger className="w-full"><SelectValue placeholder="Choose a coworker" /></SelectTrigger>
        <SelectContent>{coworkers.map((coworker) => <SelectItem key={coworker.id} value={coworker.id}>{coworker.name}</SelectItem>)}</SelectContent>
      </Select>
      <Card><CardHeader><CardTitle>{editingId ? "Edit memory" : "Add a memory"}</CardTitle></CardHeader><CardContent className="flex flex-col gap-3">
        <Textarea rows={4} value={content} onChange={(event) => setContent(event.target.value)} placeholder="A preference, fact, or decision this coworker should remember" />
        <div className="flex gap-2"><Button onClick={save} disabled={busy || !content.trim()}><PlusIcon data-icon="inline-start" />{busy ? "Saving..." : editingId ? "Save changes" : "Remember this"}</Button>{editingId ? <Button variant="outline" onClick={() => { setEditingId(null); setContent(""); }}>Cancel</Button> : null}</div>
      </CardContent></Card>
      {entries.length === 0 ? <Card><CardContent className="flex flex-col items-center gap-2 py-12 text-center"><BrainIcon className="size-9 text-muted-foreground" /><p className="font-medium">No memories yet</p><p className="text-sm text-muted-foreground">Memories appear here after conversations or manual entry.</p></CardContent></Card> : <div className="flex flex-col gap-3">{entries.map((entry) => <Card key={entry.id}><CardContent className="flex items-start justify-between gap-4"><div className="min-w-0"><div className="mb-2 flex items-center gap-2"><Badge variant="outline">{entry.source_type.replace("_", " ")}</Badge><span className="text-xs text-muted-foreground">{new Date(entry.created_at).toLocaleString()}</span></div><p className="whitespace-pre-wrap text-sm">{entry.content}</p></div><div className="flex shrink-0 gap-1"><Button size="icon-sm" variant="ghost" aria-label="Edit memory" onClick={() => { setEditingId(entry.id); setContent(entry.content); }}><PencilIcon /></Button><Button size="icon-sm" variant="ghost" aria-label="Delete memory" onClick={() => void remove(entry.id)}><Trash2Icon /></Button></div></CardContent></Card>)}</div>}
    </div>
  );
}
