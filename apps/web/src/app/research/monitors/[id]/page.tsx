"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeftIcon, PauseIcon, PlayIcon, RefreshCwIcon, Trash2Icon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiRequestError, apiFetch } from "@/lib/api";
import { getTokens } from "@/lib/auth";
import {
  getWebsiteMonitor,
  getWebsiteMonitorHistory,
  runWebsiteMonitor,
  updateWebsiteMonitor,
} from "@/lib/research";
import type { WebsiteMonitor, WebsiteMonitorRun } from "@/lib/types";

export default function WebsiteMonitorDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [monitor, setMonitor] = useState<WebsiteMonitor | null>(null);
  const [history, setHistory] = useState<WebsiteMonitorRun[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [nextMonitor, nextHistory] = await Promise.all([
        getWebsiteMonitor(params.id),
        getWebsiteMonitorHistory(params.id),
      ]);
      setMonitor(nextMonitor);
      setHistory(nextHistory);
      setError(null);
      return nextHistory;
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Couldn't load this website monitor.");
      return [];
    }
  }, [params.id]);

  useEffect(() => {
    if (!getTokens()) {
      router.push("/login");
      return;
    }
    let timer: number | undefined;
    let disposed = false;
    const poll = async () => {
      const rows = await load();
      if (!disposed && rows[0] && (rows[0].status === "queued" || rows[0].status === "running")) {
        timer = window.setTimeout(poll, 2000);
      }
    };
    void poll();
    return () => {
      disposed = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [load, router]);

  async function runNow() {
    setBusy(true);
    setError(null);
    try {
      const check = await runWebsiteMonitor(params.id);
      setHistory((rows) => [check, ...rows]);
      void (async () => {
        for (let attempt = 0; attempt < 150; attempt += 1) {
          await new Promise((resolve) => window.setTimeout(resolve, 2000));
          const rows = await load();
          if (!rows[0] || !["queued", "running"].includes(rows[0].status)) break;
        }
      })();
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Couldn't start this website check.");
    } finally {
      setBusy(false);
    }
  }

  async function toggle() {
    if (!monitor) return;
    setBusy(true);
    try {
      setMonitor(await updateWebsiteMonitor(monitor.id, { enabled: !monitor.enabled }));
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Couldn't update this monitor.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!monitor || !window.confirm(`Delete “${monitor.name}” and its saved snapshots?`)) return;
    setBusy(true);
    try {
      await apiFetch(`/website-monitors/${monitor.id}`, { method: "DELETE" });
      router.push("/research/monitors");
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Couldn't delete this monitor.");
      setBusy(false);
    }
  }

  if (error && !monitor) return <main className="mx-auto w-full max-w-4xl px-4 py-10"><Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert></main>;
  if (!monitor) return <main className="mx-auto w-full max-w-4xl px-4 py-10"><p className="text-sm text-muted-foreground">Loading monitor…</p></main>;

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-8">
      <header className="grid gap-4">
        <Button asChild variant="ghost" size="sm" className="w-fit"><Link href="/research/monitors"><ArrowLeftIcon data-icon="inline-start" />Back to monitors</Link></Button>
        <div className="flex min-w-0 flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2"><Badge variant={monitor.enabled ? "secondary" : "outline"}>{monitor.enabled ? monitor.frequency : "paused"}</Badge>{monitor.use_browser ? <Badge variant="outline">JavaScript browser</Badge> : null}</div>
            <h1 className="mt-2 break-words text-2xl font-semibold">{monitor.name}</h1>
            <a href={monitor.url} target="_blank" rel="noopener noreferrer" className="mt-1 block break-all text-sm text-primary hover:underline">{monitor.url}</a>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void runNow()} disabled={busy}><RefreshCwIcon data-icon="inline-start" />Run now</Button>
            <Button variant="outline" onClick={() => void toggle()} disabled={busy}>{monitor.enabled ? <PauseIcon data-icon="inline-start" /> : <PlayIcon data-icon="inline-start" />}{monitor.enabled ? "Pause" : "Resume"}</Button>
            <Button variant="outline" className="text-destructive" onClick={() => void remove()} disabled={busy}><Trash2Icon data-icon="inline-start" />Delete</Button>
          </div>
        </div>
      </header>

      {error ? <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert> : null}

      <Card>
        <CardHeader><CardTitle>Schedule</CardTitle><CardDescription>Checks preserve each version; unchanged checks do not send a notification.</CardDescription></CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          <div><p className="text-xs text-muted-foreground">Next check</p><p className="mt-1 text-sm font-medium">{monitor.enabled ? new Date(monitor.next_run_at).toLocaleString() : "Paused"}</p></div>
          <div><p className="text-xs text-muted-foreground">Last check</p><p className="mt-1 text-sm font-medium">{monitor.last_run_at ? new Date(monitor.last_run_at).toLocaleString() : "Not checked yet"}</p></div>
          <div><p className="text-xs text-muted-foreground">Crawl limits</p><p className="mt-1 text-sm font-medium">{monitor.crawl_pages} page{monitor.crawl_pages === 1 ? "" : "s"}, depth {monitor.max_depth}</p></div>
        </CardContent>
      </Card>

      <section className="grid gap-3" aria-labelledby="monitor-history" aria-live="polite">
        <h2 id="monitor-history" className="text-lg font-semibold">Version history</h2>
        {history.length === 0 ? <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">Run the monitor to create its first baseline.</CardContent></Card> : history.map((check, index) => (
          <Card key={check.id}>
            <CardHeader>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div><CardTitle className="flex flex-wrap items-center gap-2">Check {history.length - index}<Badge variant={check.status === "failed" ? "destructive" : check.change_detected ? "default" : "outline"}>{check.status === "completed" ? (check.change_detected ? "Changed" : "No meaningful change") : check.status}</Badge></CardTitle><CardDescription>{new Date(check.created_at).toLocaleString()}{check.snapshot?.title ? ` · ${check.snapshot.title}` : ""}</CardDescription></div>
              </div>
            </CardHeader>
            <CardContent className="grid gap-3">
              {check.error_message ? <Alert variant="destructive"><AlertDescription>{check.error_message}</AlertDescription></Alert> : null}
              {check.change_summary ? <p className="text-sm">{check.change_summary}</p> : check.status === "queued" || check.status === "running" ? <p className="text-sm text-muted-foreground">Fetching and comparing the page…</p> : null}
              {check.diff ? (
                <details className="rounded-lg border">
                  <summary className="min-h-11 cursor-pointer px-3 py-3 text-sm font-medium">View retained text difference</summary>
                  <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words border-t bg-muted/40 p-3 text-xs leading-relaxed">{check.diff}</pre>
                </details>
              ) : null}
            </CardContent>
          </Card>
        ))}
      </section>
    </main>
  );
}
