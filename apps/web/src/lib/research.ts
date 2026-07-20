import { apiFetch } from "@/lib/api";
import type {
  ResearchRun,
  ResearchRunSummary,
  WebsiteMonitor,
  WebsiteMonitorRun,
} from "@/lib/types";

export type ResearchControls = {
  max_sources?: number;
  minimum_sources?: number;
  recency_days?: number;
  language?: string;
  country?: string;
  trusted_domains?: string[];
  blocked_domains?: string[];
  use_browser?: boolean;
  crawl?: boolean;
  max_pages?: number;
  max_depth?: number;
  rate_limit_seconds?: number;
  max_chars_per_page?: number;
  extraction_schema?: Record<string, unknown>;
};

export function listResearchRuns(workspaceId: string) {
  return apiFetch<ResearchRunSummary[]>(`/research-runs?workspace_id=${workspaceId}`);
}

export function getResearchRun(id: string) {
  return apiFetch<ResearchRun>(`/research-runs/${id}`);
}

export function createResearchRun(payload: {
  workspace_id: string;
  coworker_id?: string | null;
  query: string;
  mode: "deep" | "crawl" | "extraction";
  controls: ResearchControls;
}) {
  return apiFetch<ResearchRun>("/research-runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function cancelResearchRun(id: string) {
  return apiFetch<ResearchRun>(`/research-runs/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ cancel: true }),
  });
}

export function listWebsiteMonitors(workspaceId: string) {
  return apiFetch<WebsiteMonitor[]>(`/website-monitors?workspace_id=${workspaceId}`);
}

export function getWebsiteMonitor(id: string) {
  return apiFetch<WebsiteMonitor>(`/website-monitors/${id}`);
}

export function createWebsiteMonitor(payload: {
  workspace_id: string;
  coworker_id?: string | null;
  name: string;
  url: string;
  frequency: "daily" | "weekly";
  enabled: boolean;
  use_browser: boolean;
  crawl_pages: number;
  max_depth: number;
  controls: ResearchControls;
}) {
  return apiFetch<WebsiteMonitor>("/website-monitors", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateWebsiteMonitor(id: string, payload: Partial<WebsiteMonitor>) {
  return apiFetch<WebsiteMonitor>(`/website-monitors/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function runWebsiteMonitor(id: string) {
  return apiFetch<WebsiteMonitorRun>(`/website-monitors/${id}/run`, {
    method: "POST",
    body: "{}",
  });
}

export function getWebsiteMonitorHistory(id: string) {
  return apiFetch<WebsiteMonitorRun[]>(`/website-monitors/${id}/history`);
}
