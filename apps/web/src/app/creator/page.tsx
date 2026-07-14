"use client";

import { FormEvent, useEffect, useState } from "react";
import { LandmarkIcon, WalletCardsIcon } from "lucide-react";
import { useRouter } from "next/navigation";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";

type Payout = { id: string; listing: string; gross_usd: string; platform_fee_usd: string; net_payout_usd: string; status: string; created_at: string };
type PayoutData = { account: { provider: string; provider_account_id: string; enabled: boolean } | null; payouts: Payout[] };

export default function CreatorPage() {
  const router = useRouter(); const [workspaceId, setWorkspaceId] = useState(""); const [data, setData] = useState<PayoutData>({ account: null, payouts: [] }); const [accountId, setAccountId] = useState(""); const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  async function load(id: string) { setData(await apiFetch<PayoutData>(`/workspaces/${id}/payout-account`)); }
  useEffect(() => { if (!getTokens()) { router.push("/login"); return; } void getWorkspaceId().then((id) => { if (id) { setWorkspaceId(id); load(id).catch(() => setError("Couldn’t load creator payouts. Billing-admin access may be required.")); } }); }, [router]);
  async function connect(event: FormEvent) { event.preventDefault(); setBusy(true); try { await apiFetch(`/workspaces/${workspaceId}/payout-account`, { method: "POST", body: JSON.stringify({ provider: "external", provider_account_id: accountId }) }); await load(workspaceId); } catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn’t connect payout account."); } finally { setBusy(false); } }
  const pending = data.payouts.filter((p) => p.status === "pending").reduce((sum, p) => sum + Number(p.net_payout_usd), 0);
  return <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 px-4 py-10"><header><h1 className="flex items-center gap-2 text-2xl font-semibold"><WalletCardsIcon className="size-6" />Creator economy</h1><p className="text-sm text-muted-foreground">Connect a verified payout destination and track marketplace gross revenue, platform fees, and creator proceeds.</p></header>{error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}<div className="grid gap-4 sm:grid-cols-3"><Card><CardContent className="py-5"><p className="text-sm text-muted-foreground">Pending payout</p><p className="text-2xl font-semibold tabular-nums">${pending.toFixed(2)}</p></CardContent></Card><Card><CardContent className="py-5"><p className="text-sm text-muted-foreground">Transactions</p><p className="text-2xl font-semibold tabular-nums">{data.payouts.length}</p></CardContent></Card><Card><CardContent className="py-5"><p className="text-sm text-muted-foreground">Platform fee</p><p className="text-2xl font-semibold tabular-nums">15%</p></CardContent></Card></div><Card><CardHeader><CardTitle className="flex items-center gap-2"><LandmarkIcon className="size-4" />Payout destination</CardTitle></CardHeader><CardContent>{data.account ? <div className="flex items-center justify-between rounded-md border p-3"><div><p className="font-medium">{data.account.provider_account_id}</p><p className="text-xs text-muted-foreground">Provider: {data.account.provider}</p></div><Badge>{data.account.enabled ? "Connected" : "Disabled"}</Badge></div> : <form onSubmit={connect} className="flex flex-col gap-3 sm:flex-row sm:items-end"><div className="grid flex-1 gap-1.5"><Label htmlFor="payout-account">Provider account ID</Label><Input id="payout-account" value={accountId} onChange={(e) => setAccountId(e.target.value)} required /></div><Button disabled={busy || !accountId.trim()}>Connect account</Button></form>}</CardContent></Card><Card><CardHeader><CardTitle>Payout ledger</CardTitle></CardHeader><CardContent className="grid gap-2">{data.payouts.length === 0 ? <p className="py-8 text-center text-sm text-muted-foreground">No paid marketplace orders yet.</p> : data.payouts.map((p) => <div key={p.id} className="grid gap-2 rounded-md border p-3 sm:grid-cols-5 sm:items-center"><p className="font-medium">{p.listing}</p><p className="text-sm tabular-nums">Gross ${p.gross_usd}</p><p className="text-sm tabular-nums">Fee ${p.platform_fee_usd}</p><p className="text-sm font-medium tabular-nums">Net ${p.net_payout_usd}</p><Badge variant="outline">{p.status}</Badge></div>)}</CardContent></Card></main>;
}
