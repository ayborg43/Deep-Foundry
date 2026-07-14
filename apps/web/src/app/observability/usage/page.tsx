"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import type { UsageReport } from "@/lib/types";

const MONEY = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 4 });
const INTEGER = new Intl.NumberFormat("en-US");

export default function UsagePage() {
  const router = useRouter();
  const [range, setRange] = useState("30d");
  const [report, setReport] = useState<UsageReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getTokens()) { router.push("/login"); return; }
    const timer = window.setTimeout(() => {
      void (async () => {
        const workspace = await getWorkspaceId();
        if (!workspace) return;
        try { setReport(await apiFetch<UsageReport>(`/workspaces/${workspace}/usage?range=${range}`)); }
        catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn't load usage."); }
      })();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [range, router]);

  const maxDailyCost = Math.max(...(report?.daily.map((day) => Number(day.cost_usd)) ?? [0]), 0.000001);
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-12">
      <div className="flex items-start justify-between gap-4"><div><h1 className="text-xl font-semibold">Cost & usage</h1><p className="text-sm text-muted-foreground">Model consumption derived directly from the immutable model-call stream.</p></div><Select value={range} onValueChange={setRange}><SelectTrigger className="w-32"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="7d">Last 7 days</SelectItem><SelectItem value="30d">Last 30 days</SelectItem><SelectItem value="90d">Last 90 days</SelectItem></SelectContent></Select></div>
      {error ? <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert> : null}
      {!report ? <p className="text-sm text-muted-foreground">Loading...</p> : <>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Card><CardHeader><CardTitle className="text-sm">Total cost</CardTitle></CardHeader><CardContent className="text-2xl font-semibold">{MONEY.format(Number(report.totals.cost_usd))}</CardContent></Card><Card><CardHeader><CardTitle className="text-sm">Model calls</CardTitle></CardHeader><CardContent className="text-2xl font-semibold">{INTEGER.format(report.totals.calls)}</CardContent></Card><Card><CardHeader><CardTitle className="text-sm">Total tokens</CardTitle></CardHeader><CardContent className="text-2xl font-semibold">{INTEGER.format(report.totals.input_tokens + report.totals.output_tokens)}</CardContent></Card><Card><CardHeader><CardTitle className="text-sm">Average latency</CardTitle></CardHeader><CardContent className="text-2xl font-semibold">{INTEGER.format(Math.round(report.totals.average_latency_ms))} ms</CardContent></Card></div>
        <Card><CardHeader><CardTitle>Daily cost</CardTitle></CardHeader><CardContent>{report.daily.length === 0 ? <p className="text-sm text-muted-foreground">No model calls in this period.</p> : <div className="flex h-40 items-end gap-1" aria-label="Daily model cost chart">{report.daily.map((day) => <div key={day.date} className="group relative flex min-w-0 flex-1 flex-col items-center justify-end"><div className="w-full rounded-t bg-primary/75" style={{ height: `${Math.max(3, (Number(day.cost_usd) / maxDailyCost) * 120)}px` }} title={`${day.date}: ${MONEY.format(Number(day.cost_usd))}`} /><span className="mt-1 hidden text-[9px] text-muted-foreground sm:block">{new Date(`${day.date}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span></div>)}</div>}</CardContent></Card>
        <div className="grid gap-4 lg:grid-cols-2"><Card><CardHeader><CardTitle>By coworker</CardTitle></CardHeader><CardContent><div className="flex flex-col divide-y">{report.by_coworker.map((row) => <div key={row.coworker_id ?? "none"} className="flex items-center justify-between py-3"><div><p className="font-medium">{row.coworker_name}</p><p className="text-xs text-muted-foreground">{INTEGER.format(row.calls)} calls · {INTEGER.format(row.input_tokens + row.output_tokens)} tokens</p></div><span className="font-medium">{MONEY.format(Number(row.cost_usd))}</span></div>)}</div></CardContent></Card><Card><CardHeader><CardTitle>By provider & model</CardTitle></CardHeader><CardContent><div className="flex flex-col divide-y">{report.by_provider.map((row) => <div key={`${row.deployment_mode}-${row.model_id}`} className="flex items-center justify-between py-3"><div><p className="font-medium">{row.model_id}</p><p className="text-xs text-muted-foreground">{row.deployment_mode.replaceAll("_", " ")} · {INTEGER.format(row.calls)} calls</p></div><span className="font-medium">{MONEY.format(Number(row.cost_usd))}</span></div>)}</div></CardContent></Card></div>
      </>}
    </div>
  );
}
