"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AlertTriangleIcon, PlusIcon, MicIcon, ArrowUpIcon, BellIcon, ChevronRightIcon, InboxIcon, Wand2Icon } from "lucide-react";

import { ApprovalPolicyDialog } from "@/components/approval-policy-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LogoMark } from "@/components/logo";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import { createConversation } from "@/lib/chat";
import { useCoworkerStatuses } from "@/lib/coworker-status";
import { RISK_BADGE_CLASS, RISK_LABELS } from "@/lib/coworkers";
import type { ApprovalRequestData, BackgroundTask, Coworker, User } from "@/lib/types";

const IDEAS = [
  { icon: BellIcon, label: "Send me a daily briefing" },
  { icon: InboxIcon, label: "Organize my knowledge base" },
  { icon: Wand2Icon, label: "Customize a coworker for me" },
];

const RISK_ORDER: Record<string, number> = { dangerous: 0, sensitive: 1, safe: 2 };

type ApprovalStats = {
  pending: number;
  pending_dangerous: number;
  executed_today: number;
  auto_executed_today: number;
};

const RISK_EDGE: Record<string, string> = {
  dangerous: "border-l-destructive",
  sensitive: "border-l-amber-500/70",
};

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Morning";
  if (h < 18) return "Afternoon";
  return "Evening";
}

function timeAgo(iso: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function compactArgs(args: Record<string, unknown> | undefined): string {
  if (!args) return "";
  return Object.entries(args)
    .map(([key, value]) => {
      const rendered = typeof value === "string" ? value : JSON.stringify(value);
      return `${key}: ${rendered.length > 48 ? `${rendered.slice(0, 45)}...` : rendered}`;
    })
    .join(" · ");
}

export default function HomePage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [name, setName] = useState<string>("");
  const [coworkers, setCoworkers] = useState<Coworker[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<"chat" | "cowork">("cowork");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [approvals, setApprovals] = useState<ApprovalRequestData[]>([]);
  const [approvalStats, setApprovalStats] = useState<ApprovalStats | null>(null);
  const [approvalBusyId, setApprovalBusyId] = useState<string | null>(null);
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [policyItem, setPolicyItem] = useState<ApprovalRequestData | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const statuses = useCoworkerStatuses(workspaceId, 20_000);

  useEffect(() => {
    if (!getTokens()) {
      router.push("/login");
      return;
    }
    let timer: number | undefined;
    void (async () => {
      const id = await getWorkspaceId();
      setWorkspaceId(id);
      try {
        const me = await apiFetch<User>("/me");
        setName(me.display_name || me.email.split("@")[0]);
      } catch {
        // Greeting still works without a name.
      }
      if (id) {
        try {
          setCoworkers(await apiFetch<Coworker[]>(`/workspaces/${id}/coworkers`));
        } catch {
          // Composer will route to coworker creation if none load.
        }
        const loadApprovals = async () => {
          try {
            setApprovals(
              await apiFetch<ApprovalRequestData[]>(
                `/workspaces/${id}/approval-requests?status=pending`
              )
            );
          } catch {
            // The queue degrades to the plain launcher; /approvals still has everything.
          }
          try {
            setApprovalStats(
              await apiFetch<ApprovalStats>(`/workspaces/${id}/approval-requests/stats`)
            );
          } catch {
            // Tiles just don't render without stats.
          }
        };
        await loadApprovals();
        timer = window.setInterval(() => void loadApprovals(), 15_000);
      }
    })();
    return () => {
      if (timer !== undefined) window.clearInterval(timer);
    };
  }, [router]);

  function autosize() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }

  async function submit(text: string) {
    const content = text.trim();
    if (!content || busy) return;
    if (!workspaceId || coworkers.length === 0) {
      router.push("/coworkers/new");
      return;
    }
    setBusy(true);
    setError(null);
    const coworkerId = coworkers[0].id;
    const title = content.length > 80 ? `${content.slice(0, 77)}...` : content;
    try {
      if (mode === "chat") {
        const conv = await createConversation(workspaceId, coworkerId, title);
        router.push(`/conversations/${conv.id}?draft=${encodeURIComponent(content)}`);
      } else {
        const task = await apiFetch<BackgroundTask>("/tasks", {
          method: "POST",
          body: JSON.stringify({
            workspace_id: workspaceId,
            coworker_id: coworkerId,
            title,
            description: content,
          }),
        });
        router.push(`/tasks/${task.id}`);
      }
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn't start that. Try again.");
      setBusy(false);
    }
  }

  async function decideApproval(item: ApprovalRequestData, approve: boolean) {
    setApprovalBusyId(item.id);
    setApprovalError(null);
    try {
      await apiFetch(`/approval-requests/${item.id}/${approve ? "approve" : "deny"}`, {
        method: "POST",
      });
      setApprovals((current) => current.filter((candidate) => candidate.id !== item.id));
    } catch (err) {
      setApprovalError(
        err instanceof ApiRequestError ? err.message : "Couldn't record that decision."
      );
    } finally {
      setApprovalBusyId(null);
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void submit(input);
    }
  }

  const queue = [...approvals].sort(
    (a, b) =>
      (RISK_ORDER[a.tool_risk_classification ?? ""] ?? 3) -
        (RISK_ORDER[b.tool_risk_classification ?? ""] ?? 3) ||
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );
  const hasQueue = queue.length > 0;
  const activeIndex = Math.min(selectedIndex, Math.max(0, queue.length - 1));

  // Refs so the one-time keydown listener always sees the current queue
  // and selection without re-binding on every render.
  const queueRef = useRef(queue);
  const activeIndexRef = useRef(activeIndex);
  const decideRef = useRef(decideApproval);
  useEffect(() => {
    queueRef.current = queue;
    activeIndexRef.current = activeIndex;
    decideRef.current = decideApproval;
  });

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "TEXTAREA" || target.tagName === "INPUT" || target.isContentEditable)
      ) {
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey || queueRef.current.length === 0) return;
      const key = e.key.toLowerCase();
      if (key === "j") {
        e.preventDefault();
        setSelectedIndex((i) => Math.min(i + 1, queueRef.current.length - 1));
      } else if (key === "k") {
        e.preventDefault();
        setSelectedIndex((i) => Math.max(i - 1, 0));
      } else if (key === "a" || key === "d") {
        e.preventDefault();
        const item = queueRef.current[activeIndexRef.current];
        if (item) void decideRef.current(item, key === "a");
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    const item = queue[activeIndex];
    if (item) {
      document
        .getElementById(`approval-${item.id}`)
        ?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIndex]);

  const composer = (
    <>
      <div className="rounded-2xl border border-border bg-card p-3 shadow-[var(--shadow-md)] transition-[border-color,box-shadow] focus-within:border-primary/40 focus-within:ring-4 focus-within:ring-primary/10">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
            autosize();
          }}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder="How can I help you today?"
          aria-label="Message"
          className="max-h-52 w-full resize-none bg-transparent px-2 py-1.5 text-[0.95rem] outline-none placeholder:text-muted-foreground"
        />
        <div className="mt-1 flex items-center justify-between gap-2 px-1">
          <div className="flex items-center gap-2">
            <Button type="button" size="icon-sm" variant="ghost" aria-label="Attach" className="rounded-full">
              <PlusIcon />
            </Button>
            <div className="flex items-center rounded-full bg-secondary p-0.5 text-sm">
              <button
                type="button"
                onClick={() => setMode("chat")}
                className={`rounded-full px-3 py-1 transition-colors ${mode === "chat" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
              >
                Chat
              </button>
              <button
                type="button"
                onClick={() => setMode("cowork")}
                className={`rounded-full px-3 py-1 transition-colors ${mode === "cowork" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
              >
                Cowork
              </button>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="hidden text-sm text-muted-foreground sm:inline">DeepSeek</span>
            <Button type="button" size="icon-sm" variant="ghost" aria-label="Voice input" className="rounded-full">
              <MicIcon />
            </Button>
            <Button
              type="button"
              size="icon-sm"
              className="rounded-full"
              disabled={busy || !input.trim()}
              onClick={() => void submit(input)}
              aria-label="Send"
            >
              <ArrowUpIcon />
            </Button>
          </div>
        </div>
      </div>

      <p className="mt-2 px-1 text-xs text-muted-foreground">
        {mode === "cowork"
          ? "Cowork runs the task in the background and returns a result — with approval gates on anything risky."
          : "Chat is an interactive, streaming conversation with your coworker."}
      </p>

      {error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}
    </>
  );

  if (hasQueue) {
    return (
      <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-4 py-10">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight sm:text-[1.75rem]">
              {greeting()}{name ? `, ${name}` : ""}
            </h1>
            <p className="mt-1.5 text-sm text-muted-foreground">
              Your coworkers need{" "}
              <span className="font-medium text-foreground">
                {queue.length} {queue.length === 1 ? "decision" : "decisions"}
              </span>{" "}
              before they can continue. Review each action below.
            </p>
          </div>
          <div className="hidden items-center gap-1.5 text-xs text-muted-foreground md:flex">
            Navigate
            <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px]">J</kbd>
            <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px]">K</kbd>
            <span className="mx-0.5">·</span>
            <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px]">A</kbd>
            approve
            <span className="mx-0.5">·</span>
            <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px]">D</kbd>
            deny
          </div>
        </header>

        <section aria-label="Decision stats" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-xl border bg-card px-4 py-3">
            <p className="text-xs text-muted-foreground">Pending</p>
            <p className="text-2xl font-semibold">{queue.length}</p>
          </div>
          <div className="rounded-xl border bg-card px-4 py-3">
            <p className="flex items-center gap-1 text-xs text-destructive">
              <AlertTriangleIcon className="size-3" />
              Dangerous
            </p>
            <p className="text-2xl font-semibold">
              {queue.filter((item) => item.tool_risk_classification === "dangerous").length}
            </p>
          </div>
          <div className="rounded-xl border bg-card px-4 py-3">
            <p className="text-xs text-muted-foreground">Auto-approved today</p>
            <p className="text-2xl font-semibold">
              {approvalStats ? approvalStats.auto_executed_today : "—"}
            </p>
          </div>
          <div className="rounded-xl border bg-card px-4 py-3">
            <p className="text-xs text-muted-foreground">Coworkers active</p>
            <p className="text-2xl font-semibold">
              {statuses.size > 0 ? (
                <>
                  {
                    [...statuses.values()].filter(
                      (s) => s.state === "working" || s.state === "needs_approval"
                    ).length
                  }
                  <span className="text-sm font-normal text-muted-foreground">
                    /{statuses.size}
                  </span>
                </>
              ) : (
                "—"
              )}
            </p>
          </div>
        </section>

        <section aria-label="Approval queue" className="flex flex-col gap-3">
          <div className="flex items-baseline justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Approval queue
            </h2>
            <span className="text-xs text-muted-foreground">Sorted by risk, then time</span>
          </div>

          {approvalError ? <p className="text-sm text-destructive">{approvalError}</p> : null}

          {queue.map((item, index) => {
            const risk = item.tool_risk_classification;
            const actor = item.coworker_name ?? "Coworker";
            const args = compactArgs(item.requested_action.arguments);
            const chatHref = item.conversation_id
              ? `/conversations/${item.conversation_id}`
              : item.task_id
                ? `/tasks/${item.task_id}`
                : null;
            return (
              <article
                key={item.id}
                id={`approval-${item.id}`}
                onMouseEnter={() => setSelectedIndex(index)}
                aria-label={`${actor} wants to run ${item.tool_name}`}
                className={`flex flex-col gap-3 rounded-xl border border-l-2 bg-card p-4 ${RISK_EDGE[risk ?? ""] ?? "border-l-border"}${index === activeIndex ? " ring-2 ring-primary/30" : ""}`}
              >
                <div className="flex min-w-0 items-center gap-2">
                  <span className="font-medium">{actor}</span>
                  {item.task_title ? (
                    <span className="truncate text-xs text-muted-foreground">
                      · {item.task_title}
                    </span>
                  ) : null}
                  {risk ? (
                    <Badge className={RISK_BADGE_CLASS[risk]}>{RISK_LABELS[risk]}</Badge>
                  ) : null}
                  <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                    {timeAgo(item.created_at)}
                  </span>
                </div>
                <div className="flex flex-col gap-0.5">
                  <p className="font-heading font-medium">
                    {item.summary || `${actor} wants to run ${item.tool_name}`}
                  </p>
                  {item.rationale ? (
                    <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                      {item.rationale}
                    </p>
                  ) : null}
                </div>
                <div className="rounded-lg bg-muted/60 px-3 py-2 font-mono text-xs">
                  <span className="text-muted-foreground">$ </span>
                  {item.tool_name}
                  {args ? (
                    <div className="mt-0.5 line-clamp-2 break-all text-muted-foreground">
                      {args}
                    </div>
                  ) : null}
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    disabled={approvalBusyId === item.id}
                    onClick={() => void decideApproval(item, true)}
                    aria-label={`Approve ${item.tool_name} for ${actor}`}
                  >
                    Approve
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={approvalBusyId === item.id}
                    onClick={() => void decideApproval(item, false)}
                    aria-label={`Deny ${item.tool_name} for ${actor}`}
                  >
                    Deny
                  </Button>
                  <button
                    type="button"
                    onClick={() => setPolicyItem(item)}
                    className="text-sm text-muted-foreground transition-colors hover:text-foreground"
                  >
                    Always allow…
                  </button>
                  {chatHref ? (
                    <Link
                      href={chatHref}
                      className="ml-auto inline-flex items-center gap-0.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
                    >
                      Open chat
                      <ChevronRightIcon className="size-3.5" />
                    </Link>
                  ) : null}
                </div>
              </article>
            );
          })}
        </section>

        <div>{composer}</div>

        {policyItem && workspaceId ? (
          <ApprovalPolicyDialog
            open={policyItem !== null}
            onOpenChange={(open) => !open && setPolicyItem(null)}
            workspaceId={workspaceId}
            coworkerId={policyItem.coworker_id}
            coworkerName={policyItem.coworker_name ?? "this coworker"}
            toolId={policyItem.tool_id}
            toolName={policyItem.tool_name}
            args={policyItem.requested_action.arguments ?? {}}
          />
        ) : null}
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center px-4 py-16">
      {/* Greeting */}
      <div className="mb-8 flex flex-col items-center gap-3.5 text-center">
        <LogoMark className="size-10" />
        <h1 className="text-2xl font-semibold tracking-tight text-balance sm:text-[1.75rem]">
          {greeting()}{name ? `, ${name}` : ""}
        </h1>
      </div>

      {composer}

      {/* Ideas */}
      <div className="mt-10">
        <p className="mb-1 px-1 text-sm text-muted-foreground">Ideas for you</p>
        <ul>
          {IDEAS.map((idea) => {
            const Icon = idea.icon;
            return (
              <li key={idea.label}>
                <button
                  type="button"
                  onClick={() => {
                    setInput(idea.label);
                    textareaRef.current?.focus();
                  }}
                  className="flex w-full items-center gap-3 rounded-lg px-2 py-2.5 text-left text-[0.95rem] transition-colors hover:bg-accent"
                >
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
                    <Icon className="size-4" />
                  </span>
                  {idea.label}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
