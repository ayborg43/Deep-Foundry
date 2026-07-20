"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { ArrowRightIcon, Globe2Icon, PlusIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiRequestError, apiFetch } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import { createWebsiteMonitor, listWebsiteMonitors } from "@/lib/research";
import type { Coworker, WebsiteMonitor } from "@/lib/types";

export default function WebsiteMonitorsPage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState("");
  const [monitors, setMonitors] = useState<WebsiteMonitor[]>([]);
  const [coworkers, setCoworkers] = useState<Coworker[]>([]);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [frequency, setFrequency] = useState<"daily" | "weekly">("daily");
  const [coworkerId, setCoworkerId] = useState("__none");
  const [crawlPages, setCrawlPages] = useState("1");
  const [maxDepth, setMaxDepth] = useState("0");
  const [useBrowser, setUseBrowser] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load(id: string) {
    const [rows, coworkerRows] = await Promise.all([
      listWebsiteMonitors(id),
      apiFetch<Coworker[]>(`/workspaces/${id}/coworkers`),
    ]);
    setMonitors(rows);
    setCoworkers(coworkerRows);
  }

  useEffect(() => {
    if (!getTokens()) {
      router.push("/login");
      return;
    }
    void (async () => {
      const id = await getWorkspaceId();
      if (!id) {
        setError("Couldn't determine your workspace.");
        setLoading(false);
        return;
      }
      setWorkspaceId(id);
      try {
        await load(id);
      } catch (caught) {
        setError(caught instanceof ApiRequestError ? caught.message : "Couldn't load website monitors.");
      } finally {
        setLoading(false);
      }
    })();
  }, [router]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!workspaceId || !name.trim() || !url.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const monitor = await createWebsiteMonitor({
        workspace_id: workspaceId,
        coworker_id: coworkerId === "__none" ? null : coworkerId,
        name: name.trim(),
        url: url.trim(),
        frequency,
        enabled: true,
        use_browser: useBrowser,
        crawl_pages: Number(crawlPages),
        max_depth: Number(maxDepth),
        controls: {},
      });
      router.push(`/research/monitors/${monitor.id}`);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Couldn't create this monitor.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-4 py-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div><h1 className="flex items-center gap-2 text-2xl font-semibold"><Globe2Icon className="size-6" />Website monitoring</h1><p className="mt-1 max-w-2xl text-sm text-muted-foreground">Check public pages daily or weekly, preserve versions, and notify you when content changes meaningfully.</p></div>
        <Button asChild variant="outline"><Link href="/research">Research workspace</Link></Button>
      </header>

      {error ? <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert> : null}

      <Card>
        <CardHeader><CardTitle>Monitor a website</CardTitle><CardDescription>The first check creates a baseline. Later checks retain snapshots and show bounded text differences.</CardDescription></CardHeader>
        <CardContent>
          <form onSubmit={create} className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-1.5"><Label htmlFor="monitor-name">Name</Label><Input id="monitor-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Competitor pricing" required /></div>
            <div className="grid gap-1.5"><Label htmlFor="monitor-url">Public URL</Label><Input id="monitor-url" type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com/pricing" required /></div>
            <div className="grid gap-1.5"><Label htmlFor="monitor-frequency">Frequency</Label><Select value={frequency} onValueChange={(value) => setFrequency(value as "daily" | "weekly")}><SelectTrigger id="monitor-frequency" className="h-11 w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="daily">Daily</SelectItem><SelectItem value="weekly">Weekly</SelectItem></SelectContent></Select></div>
            <div className="grid gap-1.5"><Label htmlFor="monitor-coworker">Coworker (optional)</Label><Select value={coworkerId} onValueChange={setCoworkerId}><SelectTrigger id="monitor-coworker" className="h-11 w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="__none">Use workspace defaults</SelectItem>{coworkers.map((coworker) => <SelectItem key={coworker.id} value={coworker.id}>{coworker.name}</SelectItem>)}</SelectContent></Select></div>
            <div className="grid gap-1.5"><Label htmlFor="monitor-pages">Pages per check</Label><Input id="monitor-pages" type="number" min={1} max={50} value={crawlPages} onChange={(event) => setCrawlPages(event.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="monitor-depth">Maximum depth</Label><Input id="monitor-depth" type="number" min={0} max={3} value={maxDepth} onChange={(event) => setMaxDepth(event.target.value)} /></div>
            <label className="flex min-h-11 items-center gap-3 rounded-lg border px-3 py-2 text-sm sm:col-span-2">
              <input type="checkbox" checked={useBrowser} onChange={(event) => setUseBrowser(event.target.checked)} className="size-4" />
              Render JavaScript in the isolated browser for each check
            </label>
            <Button className="min-h-11 w-fit sm:col-span-2" disabled={busy || !name.trim() || !url.trim()}><PlusIcon data-icon="inline-start" />{busy ? "Creating…" : "Create monitor"}</Button>
          </form>
        </CardContent>
      </Card>

      <section className="grid gap-3" aria-labelledby="active-monitors">
        <h2 id="active-monitors" className="text-lg font-semibold">Monitors</h2>
        {loading ? <p className="text-sm text-muted-foreground">Loading monitors…</p> : monitors.length === 0 ? (
          <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">No websites are being monitored yet.</CardContent></Card>
        ) : monitors.map((monitor) => (
          <Link href={`/research/monitors/${monitor.id}`} key={monitor.id} className="group">
            <Card className="transition-colors group-hover:bg-muted/40">
              <CardContent className="flex min-w-0 flex-wrap items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2"><p className="font-medium">{monitor.name}</p><Badge variant={monitor.enabled ? "secondary" : "outline"}>{monitor.enabled ? monitor.frequency : "paused"}</Badge>{monitor.latest_run?.change_detected ? <Badge>Changed</Badge> : null}</div>
                  <p className="mt-1 break-all text-sm text-muted-foreground">{monitor.url}</p>
                  <p className="mt-1 text-xs text-muted-foreground">Next check {new Date(monitor.next_run_at).toLocaleString()}</p>
                </div>
                <ArrowRightIcon className="size-4 text-muted-foreground" />
              </CardContent>
            </Card>
          </Link>
        ))}
      </section>
    </main>
  );
}
