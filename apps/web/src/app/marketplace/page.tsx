"use client";

import { useEffect, useState } from "react";
import { BadgeCheckIcon, DownloadIcon, PackageIcon, SearchIcon, ShieldIcon, StarIcon, WrenchIcon } from "lucide-react";
import { useRouter } from "next/navigation";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import { RISK_BADGE_CLASS } from "@/lib/coworkers";
import type { MarketplaceListing, Tool } from "@/lib/types";

const CATEGORIES = ["All", "Support", "Data & ops", "Finance", "Security", "Content"] as const;

const compactNumber = new Intl.NumberFormat("en", { notation: "compact" });

function priceLabel(listing: MarketplaceListing): string {
  if (listing.pricing_model === "free") return "Free";
  if (listing.pricing_model === "pay_what_you_want") return "Pay what you want";
  return listing.price_usd ? `$${listing.price_usd}` : "Paid";
}

export default function MarketplacePage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState("");
  const [listings, setListings] = useState<MarketplaceListing[]>([]);
  const [toolRiskByName, setToolRiskByName] = useState<Map<string, Tool["risk_classification"]>>(new Map());
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<(typeof CATEGORIES)[number]>("All");
  const [error, setError] = useState<string | null>(null);
  const [installed, setInstalled] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState<MarketplaceListing | null>(null);
  const [detail, setDetail] = useState<MarketplaceListing | null>(null);

  async function load(search = "") {
    setListings(
      await apiFetch<MarketplaceListing[]>(
        `/marketplace/listings${search ? `?query=${encodeURIComponent(search)}` : ""}`
      )
    );
  }

  useEffect(() => {
    if (!getTokens()) {
      router.push("/login");
      return;
    }
    void (async () => {
      try {
        const [id] = await Promise.all([getWorkspaceId(), load()]);
        setWorkspaceId(id || "");
      } catch {
        setError("Couldn’t load the marketplace.");
      }
      // Risk colors for scope chips — decoration; chips stay neutral if
      // the tools list can't be fetched.
      try {
        const tools = await apiFetch<Tool[]>("/tools");
        setToolRiskByName(new Map(tools.map((t) => [t.name, t.risk_classification])));
      } catch {}
    })();
  }, [router]);

  async function install(listing: MarketplaceListing) {
    setBusy(listing.id);
    setError(null);
    try {
      await apiFetch(`/marketplace/listings/${listing.id}/install`, {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspaceId }),
      });
      setInstalled((current) => new Set(current).add(listing.id));
      setReviewing(null);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn’t install this listing.");
    } finally {
      setBusy(null);
    }
  }

  async function checkout(listing: MarketplaceListing) {
    setBusy(listing.id);
    setError(null);
    try {
      const order = await apiFetch<{ checkout_url: string | null }>(
        `/marketplace/listings/${listing.id}/checkout`,
        { method: "POST", body: JSON.stringify({ workspace_id: workspaceId }) }
      );
      if (order.checkout_url) window.location.assign(order.checkout_url);
      else setError("The order was created, but this deployment has no payment checkout URL configured.");
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn’t start checkout.");
    } finally {
      setBusy(null);
    }
  }

  function openReview(listing: MarketplaceListing) {
    setReviewing(listing);
    setDetail(null);
    void apiFetch<MarketplaceListing>(`/marketplace/listings/${listing.id}`)
      .then(setDetail)
      .catch(() => setDetail(listing)); // fall back to list data
  }

  const visible = listings.filter(
    (listing) => category === "All" || listing.category === category
  );

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-4 py-10">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <PackageIcon className="size-6" />
          Marketplace
        </h1>
        <p className="text-sm text-muted-foreground">
          Install reviewed skills, workflows, and capability packs. Every listing shows what it
          can touch <em>before</em> you install.
        </p>
      </header>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-wrap items-center gap-4">
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by category">
          {CATEGORIES.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setCategory(option)}
              aria-pressed={category === option}
              className={`rounded-full border px-3.5 py-1.5 text-sm transition-colors ${
                category === option
                  ? "border-transparent bg-foreground text-background"
                  : "text-muted-foreground hover:border-foreground/30 hover:text-foreground"
              }`}
            >
              {option}
            </button>
          ))}
        </div>
        <form
          className="ml-auto flex min-w-56 flex-1 gap-2 sm:max-w-xs"
          onSubmit={(e) => {
            e.preventDefault();
            void load(query);
          }}
        >
          <div className="relative flex-1">
            <SearchIcon className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              aria-label="Search marketplace"
              className="pl-9"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search templates"
            />
          </div>
        </form>
      </div>

      {visible.length === 0 && listings.length > 0 ? (
        <p className="py-12 text-center text-sm text-muted-foreground">
          No listings in this category yet.
        </p>
      ) : null}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-label="Marketplace listings">
        {visible.map((listing) => (
          <Card key={listing.id} className="flex flex-col">
            <CardHeader>
              <div className="flex items-baseline gap-1.5">
                <CardTitle className="text-base">{listing.name}</CardTitle>
                <span className="flex min-w-0 items-center gap-1 text-xs text-muted-foreground">
                  {listing.publisher_name ? <span className="truncate">by {listing.publisher_name}</span> : null}
                  {listing.verified_publisher && (
                    <BadgeCheckIcon aria-label="Verified publisher" className="size-3.5 shrink-0 text-primary" />
                  )}
                </span>
              </div>
            </CardHeader>
            <CardContent className="flex flex-1 flex-col gap-4">
              <p className="flex-1 text-sm text-muted-foreground">{listing.summary}</p>
              {listing.declared_tools && listing.declared_tools.length > 0 ? (
                <div className="rounded-lg border bg-muted/30 px-3 py-2">
                  <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Requests access to
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {listing.declared_tools.map((toolName) => {
                      const risk = toolRiskByName.get(toolName);
                      return (
                        <Badge
                          key={toolName}
                          variant="outline"
                          className={`font-mono text-[11px] ${risk ? RISK_BADGE_CLASS[risk] : ""}`}
                        >
                          {toolName}
                        </Badge>
                      );
                    })}
                  </div>
                </div>
              ) : null}
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1">
                  <StarIcon className="size-3.5 fill-amber-400 text-amber-400" />
                  {listing.rating ? Number(listing.rating).toFixed(1) : "—"}
                </span>
                <span className="inline-flex items-center gap-1">
                  <DownloadIcon className="size-3.5" />
                  {compactNumber.format(listing.install_count)}
                </span>
                <span className="ml-auto font-medium text-foreground">{priceLabel(listing)}</span>
              </div>
              <div className="flex gap-2">
                <Button
                  className="flex-1"
                  disabled={!workspaceId || busy === listing.id || installed.has(listing.id)}
                  onClick={() => openReview(listing)}
                >
                  {installed.has(listing.id) ? "Installed" : "Review & install"}
                </Button>
                <Button variant="outline" onClick={() => openReview(listing)}>
                  Details
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </section>

      <Dialog open={reviewing !== null} onOpenChange={(open) => !open && setReviewing(null)}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          {reviewing ? (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-1.5">
                  {reviewing.name}
                  {reviewing.verified_publisher && (
                    <BadgeCheckIcon aria-label="Verified publisher" className="size-4 text-primary" />
                  )}
                </DialogTitle>
                <DialogDescription>
                  {reviewing.publisher_name ? `by ${reviewing.publisher_name} · ` : ""}
                  {reviewing.summary}
                </DialogDescription>
              </DialogHeader>

              <div className="flex flex-col gap-4 text-sm">
                <section>
                  <h3 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    <WrenchIcon className="size-3.5" />
                    Requests access to
                  </h3>
                  {detail === null ? (
                    <p className="text-xs text-muted-foreground">Loading...</p>
                  ) : detail.declared_tools && detail.declared_tools.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {detail.declared_tools.map((toolName) => {
                        const risk = toolRiskByName.get(toolName);
                        return (
                          <Badge
                            key={toolName}
                            variant="outline"
                            className={`font-mono ${risk ? RISK_BADGE_CLASS[risk] : ""}`}
                          >
                            {toolName}
                          </Badge>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">
                      No tool access declared — this listing can&apos;t touch anything outside
                      its own instructions.
                    </p>
                  )}
                </section>

                <section>
                  <h3 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    <ShieldIcon className="size-3.5" />
                    Security review
                  </h3>
                  {(detail ?? reviewing).security_review ? (
                    <div className="flex flex-col gap-1.5">
                      <p>
                        Score {(detail ?? reviewing).security_review!.score}/100 ·{" "}
                        <Badge
                          variant={
                            (detail ?? reviewing).security_review!.status === "failed"
                              ? "destructive"
                              : "outline"
                          }
                        >
                          {(detail ?? reviewing).security_review!.status.replaceAll("_", " ")}
                        </Badge>
                      </p>
                      {(detail ?? reviewing).security_review!.findings.length > 0 ? (
                        <ul className="flex flex-col gap-1 text-xs text-muted-foreground">
                          {(detail ?? reviewing).security_review!.findings.map((finding) => (
                            <li key={finding.code}>
                              <span className="font-medium">{finding.severity}</span> ·{" "}
                              {finding.message}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  ) : (
                    <p className="text-xs text-muted-foreground">No security review published.</p>
                  )}
                </section>

                <section>
                  <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Version
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    {reviewing.latest_version ?? "Unversioned"}
                    {detail?.changelog ? ` — ${detail.changelog}` : ""}
                  </p>
                </section>
              </div>

              <DialogFooter className="items-center gap-2 sm:justify-between">
                <span className="text-sm font-medium">{priceLabel(reviewing)}</span>
                <Button
                  disabled={!workspaceId || busy === reviewing.id || installed.has(reviewing.id)}
                  onClick={() =>
                    reviewing.pricing_model === "free" ? install(reviewing) : checkout(reviewing)
                  }
                >
                  <DownloadIcon data-icon="inline-start" />
                  {installed.has(reviewing.id)
                    ? "Installed"
                    : busy === reviewing.id
                      ? "Working…"
                      : reviewing.pricing_model === "free"
                        ? `Install ${reviewing.latest_version || ""}`
                        : "Buy and install"}
                </Button>
              </DialogFooter>
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </main>
  );
}
