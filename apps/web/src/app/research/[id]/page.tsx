"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeftIcon, DownloadIcon, FileJsonIcon, StopCircleIcon, TriangleAlertIcon } from "lucide-react";

import { FormattedMessage } from "@/components/formatted-message";
import { ResearchProgress } from "@/components/research/research-progress";
import { EvidenceList, ViewSources, evidenceFromSources } from "@/components/research/source-panel";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiRequestError, apiDownload } from "@/lib/api";
import { getTokens } from "@/lib/auth";
import { cancelResearchRun, getResearchRun } from "@/lib/research";
import type { ResearchRun } from "@/lib/types";

const FINISHED = new Set(["completed", "failed", "cancelled"]);

function renderValue(value: unknown) {
  if (Array.isArray(value)) return value.join(", ");
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value ?? "");
}

export default function ResearchRunPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [run, setRun] = useState<ResearchRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const next = await getResearchRun(params.id);
      setRun(next);
      setError(null);
      return next;
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Couldn't load this research run.");
      return null;
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
      const next = await load();
      if (!disposed && next && !FINISHED.has(next.status)) {
        timer = window.setTimeout(poll, 2000);
      }
    };
    void poll();
    return () => {
      disposed = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [load, router]);

  const evidence = useMemo(() => evidenceFromSources(run?.sources ?? []), [run?.sources]);

  async function cancel() {
    if (!run) return;
    setBusy(true);
    try {
      setRun(await cancelResearchRun(run.id));
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Couldn't cancel this run.");
    } finally {
      setBusy(false);
    }
  }

  async function download(format: "json" | "csv" | "markdown") {
    if (!run) return;
    setBusy(true);
    try {
      await apiDownload(`/research-runs/${run.id}/exports/${format}`, `research-${run.id}.${format === "markdown" ? "md" : format}`);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Couldn't download this export.");
    } finally {
      setBusy(false);
    }
  }

  if (error && !run) {
    return <main className="mx-auto w-full max-w-4xl px-4 py-10"><Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert></main>;
  }
  if (!run) {
    return <main className="mx-auto w-full max-w-4xl px-4 py-10"><p className="text-sm text-muted-foreground">Loading research…</p></main>;
  }

  const active = !FINISHED.has(run.status);
  return (
    <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-4 py-8">
      <header className="grid gap-4">
        <Button asChild variant="ghost" size="sm" className="w-fit"><Link href="/research"><ArrowLeftIcon data-icon="inline-start" />Back to research</Link></Button>
        <div className="flex min-w-0 flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 max-w-4xl">
            <div className="flex flex-wrap items-center gap-2"><Badge variant={run.status === "failed" ? "destructive" : run.status === "completed" ? "secondary" : "outline"}>{run.status}</Badge><span className="text-xs uppercase tracking-wide text-muted-foreground">{run.mode}</span></div>
            <h1 className="mt-2 break-words text-2xl font-semibold">{run.query}</h1>
            <p className="mt-1 text-sm text-muted-foreground">{run.sources.length} sources · Created {new Date(run.created_at).toLocaleString()}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {active ? <Button variant="outline" onClick={cancel} disabled={busy || run.cancel_requested}><StopCircleIcon data-icon="inline-start" />{run.cancel_requested ? "Stopping…" : "Cancel"}</Button> : null}
            {run.status === "completed" ? (
              <>
                <Button variant="outline" onClick={() => void download("markdown")} disabled={busy}><DownloadIcon data-icon="inline-start" />Markdown</Button>
                <Button variant="outline" onClick={() => void download("json")} disabled={busy}><FileJsonIcon data-icon="inline-start" />JSON</Button>
                {run.extraction ? <Button variant="outline" onClick={() => void download("csv")} disabled={busy}><DownloadIcon data-icon="inline-start" />CSV</Button> : null}
              </>
            ) : null}
          </div>
        </div>
      </header>

      {error ? <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert> : null}
      {run.error_message ? <Alert variant="destructive"><AlertTitle>Research failed</AlertTitle><AlertDescription>{run.error_message}</AlertDescription></Alert> : null}
      {run.weak_evidence ? (
        <Alert>
          <TriangleAlertIcon />
          <AlertTitle>Evidence needs caution</AlertTitle>
          <AlertDescription><ul className="list-disc pl-4">{run.weak_evidence_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></AlertDescription>
        </Alert>
      ) : null}

      <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="grid min-w-0 content-start gap-6">
          <Card>
            <CardHeader><CardTitle>Research progress</CardTitle><CardDescription>Progress is saved between stages and can resume safely after a worker restart.</CardDescription></CardHeader>
            <CardContent><ResearchProgress progress={run.progress} stage={run.current_stage} steps={run.steps} /></CardContent>
          </Card>

          {run.conflicts.length ? (
            <Card>
              <CardHeader><CardTitle>Conflicting evidence</CardTitle><CardDescription>These differences were found while comparing sources.</CardDescription></CardHeader>
              <CardContent className="grid gap-3">
                {run.conflicts.map((conflict, index) => (
                  <div key={`${conflict.claim}-${index}`} className="rounded-lg border p-3">
                    <p className="font-medium">{conflict.claim}</p>
                    <p className="mt-1 text-sm text-muted-foreground">{conflict.explanation}</p>
                    <p className="mt-2 text-xs">Sources: {conflict.sources.map((source) => `S${source}`).join(", ")}</p>
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}

          {run.report_markdown ? (
            <Card>
              <CardHeader>
                <CardTitle>Report</CardTitle>
                <CardDescription>Important factual claims use stable source markers such as [S1].</CardDescription>
              </CardHeader>
              <CardContent className="min-w-0">
                <FormattedMessage content={run.report_markdown} />
                <ViewSources items={evidence} />
              </CardContent>
            </Card>
          ) : null}

          {run.extraction ? (
            <Card>
              <CardHeader><CardTitle>Structured data</CardTitle><CardDescription>Validated against the requested field schema.</CardDescription></CardHeader>
              <CardContent className="grid gap-4">
                {run.extraction.warnings.map((warning) => <Alert key={warning}><AlertDescription>{warning}</AlertDescription></Alert>)}
                <dl className="grid gap-2 sm:hidden">
                  {Object.entries(run.extraction.data).map(([field, value]) => (
                    <div key={field} className="min-w-0 rounded-lg border p-3">
                      <dt className="font-medium">{field}</dt>
                      <dd className="mt-1 break-words text-sm text-muted-foreground">{renderValue(value)}</dd>
                    </div>
                  ))}
                </dl>
                <div className="hidden overflow-hidden rounded-lg border sm:block">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-muted"><tr><th className="px-3 py-2 font-medium">Field</th><th className="px-3 py-2 font-medium">Extracted value</th></tr></thead>
                    <tbody>{Object.entries(run.extraction.data).map(([field, value]) => <tr key={field} className="border-t"><th className="px-3 py-2 align-top font-medium">{field}</th><td className="break-words px-3 py-2">{renderValue(value)}</td></tr>)}</tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          ) : null}
        </div>

        <aside className="hidden min-w-0 lg:block" aria-label="Research evidence">
          <div className="sticky top-24 grid max-h-[calc(100vh-7rem)] gap-3 overflow-y-auto pr-1">
            <div><h2 className="font-semibold">Sources and evidence</h2><p className="text-sm text-muted-foreground">{evidence.length} retained passage{evidence.length === 1 ? "" : "s"}</p></div>
            {evidence.length ? <EvidenceList items={evidence} /> : <p className="rounded-lg border p-4 text-sm text-muted-foreground">Sources will appear as they are read.</p>}
          </div>
        </aside>
      </div>
    </main>
  );
}
