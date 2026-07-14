"use client";

import { useEffect, useState } from "react";
import { BadgeCheckIcon, DownloadIcon, PackageIcon, SearchIcon } from "lucide-react";
import { useRouter } from "next/navigation";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import type { MarketplaceListing } from "@/lib/types";

export default function MarketplacePage() {
  const router = useRouter(); const [workspaceId, setWorkspaceId] = useState("");
  const [listings, setListings] = useState<MarketplaceListing[]>([]); const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null); const [installed, setInstalled] = useState<Set<string>>(new Set()); const [busy, setBusy] = useState<string | null>(null);
  async function load(search = "") { setListings(await apiFetch<MarketplaceListing[]>(`/marketplace/listings${search ? `?query=${encodeURIComponent(search)}` : ""}`)); }
  useEffect(() => {
    if (!getTokens()) { router.push("/login"); return; }
    void (async () => {
      try {
        const [id] = await Promise.all([getWorkspaceId(), load()]);
        setWorkspaceId(id || "");
      } catch { setError("Couldn’t load the marketplace."); }
    })();
  }, [router]);
  async function install(listing: MarketplaceListing) { setBusy(listing.id); setError(null); try { await apiFetch(`/marketplace/listings/${listing.id}/install`, { method: "POST", body: JSON.stringify({ workspace_id: workspaceId }) }); setInstalled((current) => new Set(current).add(listing.id)); } catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn’t install this listing."); } finally { setBusy(null); } }
  async function checkout(listing: MarketplaceListing) { setBusy(listing.id); setError(null); try { const order = await apiFetch<{ checkout_url: string | null }>(`/marketplace/listings/${listing.id}/checkout`, { method: "POST", body: JSON.stringify({ workspace_id: workspaceId }) }); if (order.checkout_url) window.location.assign(order.checkout_url); else setError("The order was created, but this deployment has no payment checkout URL configured."); } catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn’t start checkout."); } finally { setBusy(null); } }
  return <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-4 py-10">
    <header><h1 className="flex items-center gap-2 text-2xl font-semibold"><PackageIcon className="size-6" />Marketplace</h1><p className="text-sm text-muted-foreground">Install reviewed skills, workflows, and complete coworker capability packs.</p></header>
    {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
    <form className="flex max-w-xl gap-2" onSubmit={(e) => { e.preventDefault(); void load(query); }}><div className="relative flex-1"><SearchIcon className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input aria-label="Search marketplace" className="pl-9" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search skills and capability packs" /></div><Button variant="outline">Search</Button></form>
    <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-label="Marketplace listings">{listings.map((listing) => <Card key={listing.id} className="flex flex-col"><CardHeader><div className="flex items-start justify-between gap-3"><CardTitle className="text-base">{listing.name}</CardTitle>{listing.verified_publisher && <BadgeCheckIcon aria-label="Verified publisher" className="size-5 text-primary" />}</div><div className="flex flex-wrap gap-2"><Badge variant="secondary">{listing.listing_type.replaceAll("_", " ")}</Badge><Badge variant="outline">{listing.pricing_model === "free" ? "Free" : `$${listing.price_usd}`}</Badge>{listing.security_review && <Badge variant={listing.security_review.status === "failed" ? "destructive" : "outline"}>Security {listing.security_review.score}/100</Badge>}</div></CardHeader><CardContent className="flex flex-1 flex-col gap-4"><p className="flex-1 text-sm text-muted-foreground">{listing.summary}</p><p className="text-xs text-muted-foreground">{listing.install_count} installs · {listing.rating ? `${Number(listing.rating).toFixed(1)} / 5` : "No reviews"}</p><Button onClick={() => listing.pricing_model === "free" ? install(listing) : checkout(listing)} disabled={!workspaceId || busy === listing.id || installed.has(listing.id)}><DownloadIcon data-icon="inline-start" />{installed.has(listing.id) ? "Installed" : busy === listing.id ? "Working…" : listing.pricing_model === "free" ? `Install ${listing.latest_version || ""}` : "Buy and install"}</Button></CardContent></Card>)}</section>
  </main>;
}
