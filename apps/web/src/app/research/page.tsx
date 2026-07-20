"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { ArrowRightIcon, Globe2Icon, SearchIcon, SparklesIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import { createResearchRun, listResearchRuns } from "@/lib/research";
import type { Coworker, ResearchRunSummary } from "@/lib/types";
import { apiFetch } from "@/lib/api";

type Mode = "deep" | "crawl" | "extraction";

const MODE_COPY: Record<Mode, { label: string; description: string; placeholder: string }> = {
  deep: {
    label: "Deep research",
    description: "Search, read, compare, and produce a cited report.",
    placeholder: "What changed in enterprise AI security requirements this year?",
  },
  crawl: {
    label: "Website crawl",
    description: "Responsibly crawl one public domain using robots.txt and sitemap rules.",
    placeholder: "https://example.com",
  },
  extraction: {
    label: "Structured extraction",
    description: "Collect defined fields and export them as JSON, CSV, or a table.",
    placeholder: "Extract product details from https://example.com/products",
  },
};

function statusVariant(status: ResearchRunSummary["status"]) {
  return status === "failed" ? "destructive" as const : status === "completed" ? "secondary" as const : "outline" as const;
}

export default function ResearchPage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState("");
  const [runs, setRuns] = useState<ResearchRunSummary[]>([]);
  const [coworkers, setCoworkers] = useState<Coworker[]>([]);
  const [mode, setMode] = useState<Mode>("deep");
  const [query, setQuery] = useState("");
  const [coworkerId, setCoworkerId] = useState("__none");
  const [maxSources, setMaxSources] = useState("8");
  const [minimumSources, setMinimumSources] = useState("3");
  const [recencyDays, setRecencyDays] = useState("");
  const [language, setLanguage] = useState("");
  const [country, setCountry] = useState("");
  const [trustedDomains, setTrustedDomains] = useState("");
  const [blockedDomains, setBlockedDomains] = useState("");
  const [maxPages, setMaxPages] = useState("10");
  const [maxDepth, setMaxDepth] = useState("1");
  const [useBrowser, setUseBrowser] = useState(false);
  const [schema, setSchema] = useState('{\n  "company": "",\n  "product": "",\n  "price": "",\n  "features": [],\n  "contact_email": ""\n}');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
        const [researchRows, coworkerRows] = await Promise.all([
          listResearchRuns(id),
          apiFetch<Coworker[]>(`/workspaces/${id}/coworkers`),
        ]);
        setRuns(researchRows);
        setCoworkers(coworkerRows);
      } catch (caught) {
        setError(caught instanceof ApiRequestError ? caught.message : "Couldn't load research.");
      } finally {
        setLoading(false);
      }
    })();
  }, [router]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!workspaceId || !query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      let extractionSchema: Record<string, unknown> | undefined;
      if (mode === "extraction") {
        try {
          extractionSchema = JSON.parse(schema) as Record<string, unknown>;
        } catch {
          setError("The extraction schema must be valid JSON.");
          return;
        }
      }
      const splitDomains = (value: string) =>
        value.split(/[\s,]+/).map((item) => item.trim()).filter(Boolean);
      const run = await createResearchRun({
        workspace_id: workspaceId,
        coworker_id: coworkerId === "__none" ? null : coworkerId,
        query: query.trim(),
        mode,
        controls: {
          max_sources: Number(maxSources),
          minimum_sources: Number(minimumSources),
          ...(recencyDays ? { recency_days: Number(recencyDays) } : {}),
          ...(language ? { language } : {}),
          ...(country ? { country } : {}),
          trusted_domains: splitDomains(trustedDomains),
          blocked_domains: splitDomains(blockedDomains),
          max_pages: Number(maxPages),
          max_depth: Number(maxDepth),
          use_browser: useBrowser,
          ...(extractionSchema ? { extraction_schema: extractionSchema } : {}),
        },
      });
      router.push(`/research/${run.id}`);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Couldn't start the research run.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-4 py-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold"><SearchIcon className="size-6" />Research</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Research public sources with verifiable passages, quality controls, responsible crawling, and downloadable results.
          </p>
        </div>
        <Button asChild variant="outline"><Link href="/research/monitors"><Globe2Icon data-icon="inline-start" />Website monitors</Link></Button>
      </header>

      {error ? <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert> : null}

      <Card>
        <CardHeader>
          <CardTitle>Start research</CardTitle>
          <CardDescription>Choose a mode. The browser option is isolated and only runs when explicitly enabled.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="grid gap-5">
            <fieldset className="grid gap-2 sm:grid-cols-3">
              <legend className="sr-only">Research mode</legend>
              {(Object.keys(MODE_COPY) as Mode[]).map((item) => (
                <button
                  type="button"
                  key={item}
                  aria-pressed={mode === item}
                  onClick={() => setMode(item)}
                  className={`min-h-24 rounded-lg border p-3 text-left transition-colors ${mode === item ? "border-primary bg-primary/5 ring-1 ring-primary" : "hover:bg-muted"}`}
                >
                  <span className="font-medium">{MODE_COPY[item].label}</span>
                  <span className="mt-1 block text-sm text-muted-foreground">{MODE_COPY[item].description}</span>
                </button>
              ))}
            </fieldset>

            <div className="grid gap-1.5">
              <Label htmlFor="research-query">{mode === "crawl" ? "Starting URL" : "Question or source"}</Label>
              <Textarea id="research-query" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={MODE_COPY[mode].placeholder} rows={4} required />
            </div>

            {mode === "extraction" ? (
              <div className="grid gap-1.5">
                <Label htmlFor="extraction-schema">Fields to extract (JSON)</Label>
                <Textarea id="extraction-schema" value={schema} onChange={(event) => setSchema(event.target.value)} rows={9} className="font-mono text-sm" spellCheck={false} />
                <p className="text-xs text-muted-foreground">Use empty strings, numbers, booleans, or arrays to describe the expected values.</p>
              </div>
            ) : null}

            <details className="rounded-lg border">
              <summary className="min-h-11 cursor-pointer px-4 py-3 font-medium">Quality and crawl controls</summary>
              <div className="grid gap-4 border-t p-4 sm:grid-cols-2 lg:grid-cols-3">
                <div className="grid gap-1.5"><Label htmlFor="research-coworker">Coworker (optional)</Label><Select value={coworkerId} onValueChange={setCoworkerId}><SelectTrigger id="research-coworker" className="h-11 w-full"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="__none">Use workspace defaults</SelectItem>{coworkers.map((coworker) => <SelectItem key={coworker.id} value={coworker.id}>{coworker.name}</SelectItem>)}</SelectContent></Select></div>
                <div className="grid gap-1.5"><Label htmlFor="max-sources">Maximum sources</Label><Input id="max-sources" type="number" min={2} max={20} value={maxSources} onChange={(event) => setMaxSources(event.target.value)} /></div>
                <div className="grid gap-1.5"><Label htmlFor="minimum-sources">Minimum sources</Label><Input id="minimum-sources" type="number" min={1} max={10} value={minimumSources} onChange={(event) => setMinimumSources(event.target.value)} /></div>
                <div className="grid gap-1.5"><Label htmlFor="recency-days">Published within days</Label><Input id="recency-days" type="number" min={1} max={3650} value={recencyDays} onChange={(event) => setRecencyDays(event.target.value)} placeholder="Any time" /></div>
                <div className="grid gap-1.5"><Label htmlFor="language">Language</Label><Input id="language" value={language} onChange={(event) => setLanguage(event.target.value)} placeholder="en" maxLength={10} /></div>
                <div className="grid gap-1.5"><Label htmlFor="country">Country</Label><Input id="country" value={country} onChange={(event) => setCountry(event.target.value.toUpperCase())} placeholder="NG" maxLength={2} /></div>
                <div className="grid gap-1.5"><Label htmlFor="trusted-domains">Trusted domains</Label><Input id="trusted-domains" value={trustedDomains} onChange={(event) => setTrustedDomains(event.target.value)} placeholder="who.int, gov.uk" /></div>
                <div className="grid gap-1.5"><Label htmlFor="blocked-domains">Blocked domains</Label><Input id="blocked-domains" value={blockedDomains} onChange={(event) => setBlockedDomains(event.target.value)} placeholder="example.net" /></div>
                <div className="grid gap-1.5"><Label htmlFor="max-pages">Maximum pages</Label><Input id="max-pages" type="number" min={1} max={50} value={maxPages} onChange={(event) => setMaxPages(event.target.value)} /></div>
                <div className="grid gap-1.5"><Label htmlFor="max-depth">Crawl depth</Label><Input id="max-depth" type="number" min={0} max={3} value={maxDepth} onChange={(event) => setMaxDepth(event.target.value)} /></div>
                <label className="flex min-h-11 items-center gap-3 self-end rounded-lg border px-3 py-2 text-sm">
                  <input type="checkbox" checked={useBrowser} onChange={(event) => setUseBrowser(event.target.checked)} className="size-4" />
                  Use isolated JavaScript browser
                </label>
              </div>
            </details>

            <Button className="min-h-11 w-fit" disabled={busy || !query.trim()}>
              <SparklesIcon data-icon="inline-start" />{busy ? "Starting…" : `Start ${MODE_COPY[mode].label.toLowerCase()}`}
            </Button>
          </form>
        </CardContent>
      </Card>

      <section className="grid gap-3" aria-labelledby="recent-research">
        <h2 id="recent-research" className="text-lg font-semibold">Recent research</h2>
        {loading ? <p className="text-sm text-muted-foreground">Loading research…</p> : runs.length === 0 ? (
          <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">No research runs yet.</CardContent></Card>
        ) : runs.map((run) => (
          <Link key={run.id} href={`/research/${run.id}`} className="group block">
            <Card className="transition-colors group-hover:bg-muted/40">
              <CardContent className="flex min-w-0 flex-wrap items-center justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2"><Badge variant={statusVariant(run.status)}>{run.status}</Badge><span className="text-xs uppercase tracking-wide text-muted-foreground">{run.mode}</span></div>
                  <p className="mt-2 break-words font-medium">{run.query}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{run.source_count} sources · {new Date(run.created_at).toLocaleString()}</p>
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">{run.progress}%<ArrowRightIcon className="size-4" /></div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </section>
    </main>
  );
}
