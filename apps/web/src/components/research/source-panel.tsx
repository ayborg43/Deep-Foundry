"use client";

import { ExternalLinkIcon, FileTextIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { MessageCitation, ResearchSource } from "@/lib/types";
import { cn } from "@/lib/utils";

type EvidenceItem = {
  key: string;
  ordinal: number;
  claim: string;
  passage: string;
  locator: string;
  pageNumber: number | null;
  url: string;
  title: string;
  publisher: string;
  publishedAt: string | null;
  accessedAt: string;
  trustLevel?: string;
};

function formatDate(value: string | null) {
  if (!value) return "Not provided";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value));
}

export function evidenceFromSources(sources: ResearchSource[]): EvidenceItem[] {
  return sources.flatMap((source) =>
    source.evidence.map((evidence) => ({
      key: evidence.id,
      ordinal: evidence.ordinal,
      claim: evidence.claim,
      passage: evidence.passage,
      locator: evidence.locator,
      pageNumber: evidence.page_number,
      url: source.url,
      title: source.title || new URL(source.url).hostname,
      publisher: source.publisher,
      publishedAt: source.published_at,
      accessedAt: source.accessed_at,
      trustLevel: source.trust_level,
    })),
  ).sort((left, right) => left.ordinal - right.ordinal);
}

export function evidenceFromCitations(citations: MessageCitation[]): EvidenceItem[] {
  return citations.map((citation) => ({
    key: citation.id,
    ordinal: citation.ordinal,
    claim: citation.claim,
    passage: citation.passage,
    locator: citation.locator,
    pageNumber: citation.page_number,
    url: citation.canonical_url || citation.url,
    title: citation.title || new URL(citation.url).hostname,
    publisher: citation.publisher,
    publishedAt: citation.published_at,
    accessedAt: citation.accessed_at,
  }));
}

export function EvidenceList({
  items,
  className,
}: {
  items: EvidenceItem[];
  className?: string;
}) {
  return (
    <ol className={cn("grid gap-3", className)}>
      {items.map((item) => (
        <li key={item.key} id={`source-${item.ordinal}`} className="min-w-0 rounded-lg border bg-card p-3">
          <div className="flex min-w-0 items-start gap-2">
            <Badge variant="outline" className="shrink-0">S{item.ordinal}</Badge>
            <div className="min-w-0 flex-1">
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex max-w-full items-start gap-1 font-medium text-primary hover:underline"
              >
                <span className="break-words">{item.title}</span>
                <ExternalLinkIcon className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              </a>
              <p className="mt-1 break-words text-xs text-muted-foreground">
                {item.publisher ? `${item.publisher} · ` : ""}
                Published {formatDate(item.publishedAt)} · Accessed {formatDate(item.accessedAt)}
                {item.pageNumber ? ` · Page ${item.pageNumber}` : item.locator ? ` · ${item.locator}` : ""}
              </p>
              {item.claim ? <p className="mt-2 text-sm font-medium">{item.claim}</p> : null}
              <blockquote className="mt-2 break-words border-l-2 border-primary/40 pl-3 text-sm leading-relaxed text-muted-foreground">
                “{item.passage}”
              </blockquote>
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

export function ViewSources({
  items,
  label,
}: {
  items: EvidenceItem[];
  label?: string;
}) {
  if (!items.length) return null;
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button type="button" variant="outline" size="sm" className="mt-3">
          <FileTextIcon data-icon="inline-start" />
          {label ?? `View sources (${items.length})`}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Sources and supporting evidence</DialogTitle>
          <DialogDescription>
            Every passage below is retained from the fetched source so you can verify important claims.
          </DialogDescription>
        </DialogHeader>
        <EvidenceList items={items} />
      </DialogContent>
    </Dialog>
  );
}
