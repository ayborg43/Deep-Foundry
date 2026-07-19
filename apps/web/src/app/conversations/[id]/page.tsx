"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import {
  AlertTriangleIcon,
  ArrowLeftIcon,
  BotIcon,
  BrainIcon,
  CheckIcon,
  ClockIcon,
  CpuIcon,
  MicIcon,
  SendIcon,
  ShieldIcon,
  Volume2Icon,
  WrenchIcon,
  XIcon,
} from "lucide-react";

import { ApprovalPolicyDialog } from "@/components/approval-policy-dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens } from "@/lib/auth";
import { COWORKER_STATUS_META, useCoworkerStatuses } from "@/lib/coworker-status";
import {
  approveRequest,
  denyRequest,
  getConversation,
  listMessages,
  listPendingApprovalRequests,
  resumeTurn,
  sendMessage,
  type ChatSSEEvent,
} from "@/lib/chat";
import { MODEL_SHORT_LABELS, RISK_BADGE_CLASS, RISK_LABELS } from "@/lib/coworkers";
import type {
  BackgroundTask,
  ChatMessage,
  Conversation,
  Coworker,
  KnowledgeBase,
  MemoryEntry,
  RiskClassification,
  Tool,
  ToolCallRequest,
} from "@/lib/types";

type LiveToolCall = {
  toolName: string;
  arguments: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  startedAt: number;
  durationMs: number | null;
};

type PendingApproval = {
  approvalRequestId: string;
  messageId: string | null;
  toolName: string;
  arguments: Record<string, unknown>;
  summary: string;
  rationale: string;
};

function riskOf(toolsByName: Map<string, Tool>, name: string): RiskClassification | null {
  return toolsByName.get(name)?.risk_classification ?? null;
}

function EntryLines({ entries }: { entries: Record<string, unknown> }) {
  return (
    <>
      {Object.entries(entries).map(([key, value]) => (
        <div key={key} className="break-all">
          <span className="text-muted-foreground">{key}: </span>
          {typeof value === "string" ? `"${value}"` : JSON.stringify(value)}
        </div>
      ))}
    </>
  );
}

function ToolCallCard({
  toolName,
  args,
  result,
  risk,
  autoRun,
  pending,
  durationMs,
}: {
  toolName: string;
  args: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  risk: RiskClassification | null;
  autoRun: boolean;
  pending: boolean;
  durationMs?: number | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const detailsId = useId();

  return (
    <div className="flex flex-col gap-1.5 rounded-lg border bg-muted/40 px-3 py-2 text-xs">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-2 text-left"
        aria-expanded={expanded}
        aria-controls={detailsId}
        aria-label={`${toolName} tool call, ${pending ? "running" : "complete"}. ${expanded ? "Hide" : "Show"} details`}
      >
        <WrenchIcon className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="font-mono font-medium">{toolName}</span>
        {risk ? (
          <Badge className={RISK_BADGE_CLASS[risk]}>
            {RISK_LABELS[risk]}
            {autoRun ? " · auto-run" : ""}
          </Badge>
        ) : null}
        <span className="text-muted-foreground">
          {pending ? "Running..." : null}
        </span>
        <span className="ml-auto flex shrink-0 items-center gap-2 text-muted-foreground">
          {!pending && durationMs != null ? <span className="font-mono">{durationMs}ms</span> : null}
          {expanded ? "Hide" : "Details"}
        </span>
      </button>
      {expanded ? (
        <div id={detailsId} className="flex flex-col gap-1 border-t pt-2 font-mono">
          {args && Object.keys(args).length > 0 ? (
            <>
              <p className="text-muted-foreground">{"// request"}</p>
              <EntryLines entries={args} />
            </>
          ) : null}
          {result ? (
            <>
              <p className="mt-1 text-muted-foreground">{"// result"}</p>
              <EntryLines entries={result} />
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

const APPROVAL_TINT: Record<string, string> = {
  dangerous: "border-destructive/40 bg-destructive/5",
  sensitive: "border-amber-500/40 bg-amber-500/5 dark:border-amber-400/30",
};

function ApprovalCard({
  coworkerName,
  toolName,
  args,
  risk,
  summary,
  rationale,
  isDeciding,
  onApprove,
  onDeny,
  onAlwaysAllow,
}: {
  coworkerName: string;
  toolName: string;
  args: Record<string, unknown>;
  risk: RiskClassification | null;
  summary?: string;
  rationale?: string;
  isDeciding: boolean;
  onApprove: () => void;
  onDeny: () => void;
  onAlwaysAllow?: () => void;
}) {
  return (
    <div
      className={`flex flex-col gap-3 rounded-xl border px-4 py-3.5 text-sm ${APPROVAL_TINT[risk ?? ""] ?? "bg-muted/40"}`}
      role="region"
      aria-label={`Approval required for ${toolName}`}
    >
      <div className="flex items-center gap-2">
        <AlertTriangleIcon className="size-4 shrink-0 text-amber-600 dark:text-amber-400" />
        <span className="font-medium">Approval required</span>
        {risk ? (
          <Badge className={RISK_BADGE_CLASS[risk]}>{RISK_LABELS[risk]}</Badge>
        ) : null}
      </div>
      <p className="font-heading font-semibold">
        {summary || `${coworkerName} wants to run ${toolName}`}
      </p>
      {rationale ? (
        <p className="text-xs leading-relaxed text-muted-foreground">{rationale}</p>
      ) : null}
      <div
        className="flex flex-col gap-0.5 rounded-lg bg-background/70 px-3 py-2 font-mono text-xs"
        tabIndex={0}
        aria-label={`${toolName} arguments`}
      >
        <div>
          <span className="text-muted-foreground">tool </span>
          {toolName}
        </div>
        <EntryLines entries={args} />
      </div>
      <p className="text-xs text-muted-foreground">
        The conversation is paused until you approve or deny this action.
      </p>
      <div className="flex items-center gap-2">
        <Button type="button" size="sm" disabled={isDeciding} onClick={onApprove} aria-label={`Approve ${toolName}`}>
          <CheckIcon data-icon="inline-start" />
          {isDeciding ? "Working..." : "Approve & run"}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={isDeciding}
          onClick={onDeny}
          aria-label={`Deny ${toolName}`}
        >
          <XIcon data-icon="inline-start" />
          Deny
        </Button>
        {onAlwaysAllow ? (
          <button
            type="button"
            onClick={onAlwaysAllow}
            className="ml-auto text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            Always allow {toolName} →
          </button>
        ) : null}
      </div>
    </div>
  );
}

export default function ConversationPage() {
  const params = useParams<{ id: string }>();
  const conversationId = params.id;
  const router = useRouter();
  const searchParams = useSearchParams();

  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [coworker, setCoworker] = useState<Coworker | null>(null);
  const [toolsByName, setToolsByName] = useState<Map<string, Tool>>(new Map());
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Seeded from the home composer, which routes here with ?draft=...
  const [input, setInput] = useState(() => searchParams.get("draft") ?? "");
  const [isSending, setIsSending] = useState(false);
  const [turnError, setTurnError] = useState<string | null>(null);
  const [streamingText, setStreamingText] = useState("");
  const [liveToolCalls, setLiveToolCalls] = useState<LiveToolCall[]>([]);
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(null);
  const [isDeciding, setIsDeciding] = useState(false);
  const [isHandingOff, setIsHandingOff] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [memories, setMemories] = useState<MemoryEntry[] | null>(null);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[] | null>(null);
  const statuses = useCoworkerStatuses(conversation?.workspace_id ?? null, 30_000);
  const [policyDialogOpen, setPolicyDialogOpen] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);

  function startVoiceInput() {
    const browserWindow = window as typeof window & { webkitSpeechRecognition?: new () => { lang: string; interimResults: boolean; onresult: (event: { results: ArrayLike<{ 0: { transcript: string } }> }) => void; onend: () => void; onerror: () => void; start: () => void } };
    if (!browserWindow.webkitSpeechRecognition) {
      setTurnError("Voice input isn’t supported by this browser. Try Chrome or Edge.");
      return;
    }
    const recognition = new browserWindow.webkitSpeechRecognition();
    recognition.lang = navigator.language || "en-US";
    recognition.interimResults = false;
    recognition.onresult = (event) => setInput((current) => `${current}${current ? " " : ""}${event.results[0][0].transcript}`);
    recognition.onend = () => setIsListening(false);
    recognition.onerror = () => { setIsListening(false); setTurnError("Voice input stopped before a transcript was available."); };
    setIsListening(true); recognition.start();
  }

  function speakLatestReply() {
    const content = [...messages].reverse().find((message) => message.sender_type === "coworker" && message.content)?.content || streamingText;
    if (!content || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel(); window.speechSynthesis.speak(new SpeechSynthesisUtterance(content));
  }

  async function handleBackgroundHandoff() {
    const description = input.trim();
    if (!description) return;
    setIsHandingOff(true);
    setTurnError(null);
    try {
      const task = await apiFetch<BackgroundTask>(`/conversations/${conversationId}/tasks`, {
        method: "POST",
        body: JSON.stringify({
          title: description.length > 80 ? `${description.slice(0, 77)}...` : description,
          description,
        }),
      });
      setInput("");
      router.push(`/tasks/${task.id}`);
    } catch (err) {
      setTurnError(err instanceof ApiRequestError ? err.message : "Couldn't hand off this task.");
      setIsHandingOff(false);
    }
  }

  useEffect(() => {
    if (!getTokens()) {
      router.push("/login");
      return;
    }
    if (!conversationId) return;

    async function load() {
      setIsLoading(true);
      setLoadError(null);
      try {
        const conv = await getConversation(conversationId);
        setConversation(conv);
        if (!conv.coworker_id) {
          throw new Error("This conversation has no coworker participant.");
        }

        const [cw, tools, history] = await Promise.all([
          apiFetch<Coworker>(`/coworkers/${conv.coworker_id}`),
          apiFetch<Tool[]>("/tools"),
          listMessages(conversationId),
        ]);
        setCoworker(cw);
        setToolsByName(new Map(tools.map((t) => [t.name, t])));
        setMessages(history);

        // Dossier data is best-effort — each section simply stays hidden
        // if its fetch fails.
        void apiFetch<MemoryEntry[]>(`/memory/coworker/${cw.id}/timeline`)
          .then(setMemories)
          .catch(() => {});
        void apiFetch<KnowledgeBase[]>(`/knowledge-bases?workspace_id=${conv.workspace_id}`)
          .then((bases) =>
            setKnowledgeBases(
              bases.filter(
                (base) =>
                  base.attached_coworker_ids.includes(cw.id) ||
                  (base.scope === "coworker" && base.scope_id === cw.id)
              )
            )
          )
          .catch(() => {});

        const pending = await listPendingApprovalRequests(conv.workspace_id);
        const mine = pending.find((ar) => ar.conversation_id === conversationId);
        if (mine) {
          setPendingApproval({
            approvalRequestId: mine.id,
            messageId: mine.message_id,
            toolName: mine.tool_name,
            arguments: mine.requested_action.arguments ?? {},
            summary: mine.summary ?? "",
            rationale: mine.rationale ?? "",
          });
        }
      } catch (err) {
        setLoadError(
          err instanceof ApiRequestError
            ? err.message
            : err instanceof Error
              ? err.message
              : "Couldn't load this conversation."
        );
      } finally {
        setIsLoading(false);
      }
    }

    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, streamingText, liveToolCalls, pendingApproval]);

  function resetTurnState() {
    setStreamingText("");
    setLiveToolCalls([]);
  }

  async function refreshMessages() {
    try {
      const history = await listMessages(conversationId);
      setMessages(history);
    } catch {
      // Keep whatever we already have; the next manual reload will recover.
    }
  }

  async function handleEvent(event: ChatSSEEvent) {
    if (event.event === "token") {
      setStreamingText((prev) => prev + event.data.delta);
    } else if (event.event === "tool_call_started") {
      setLiveToolCalls((prev) => [
        ...prev,
        {
          toolName: event.data.tool_name,
          arguments: event.data.arguments,
          result: null,
          startedAt: Date.now(),
          durationMs: null,
        },
      ]);
    } else if (event.event === "tool_call_result") {
      setLiveToolCalls((prev) => {
        const idx = prev
          .map((c, i) => ({ c, i }))
          .reverse()
          .find(({ c }) => c.toolName === event.data.tool_name && c.result === null)?.i;
        if (idx === undefined) {
          return [
            ...prev,
            {
              toolName: event.data.tool_name,
              arguments: null,
              result: event.data.result,
              startedAt: Date.now(),
              durationMs: null,
            },
          ];
        }
        const next = [...prev];
        next[idx] = {
          ...next[idx],
          result: event.data.result,
          durationMs: Date.now() - next[idx].startedAt,
        };
        return next;
      });
    } else if (event.event === "approval_required") {
      setPendingApproval({
        approvalRequestId: event.data.approval_request_id,
        messageId: event.data.message_id,
        toolName: event.data.tool_name,
        arguments: event.data.arguments,
        summary: event.data.summary ?? "",
        rationale: event.data.rationale ?? "",
      });
      setIsSending(false);
    } else if (event.event === "message_complete") {
      resetTurnState();
      setIsSending(false);
      await refreshMessages();
    } else if (event.event === "error") {
      setTurnError(event.data.detail);
      resetTurnState();
      setIsSending(false);
      await refreshMessages();
    }
  }

  async function handleSend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = input.trim();
    if (!content || isSending || pendingApproval) return;

    setInput("");
    setIsSending(true);
    setTurnError(null);
    resetTurnState();
    // Optimistic local echo of the user's own message — the authoritative
    // row comes back on the refreshMessages() that follows message_complete.
    setMessages((prev) => [
      ...prev,
      {
        id: `local-${Date.now()}`,
        conversation_id: conversationId,
        sender_type: "user",
        sender_id: null,
        content,
        tool_calls: null,
        tool_call_id: null,
        parent_message_id: null,
        status: "complete",
        created_at: new Date().toISOString(),
      },
    ]);

    try {
      await sendMessage(conversationId, content, handleEvent);
    } catch (err) {
      setTurnError(
        err instanceof ApiRequestError ? err.message : "Couldn't send that message."
      );
      setIsSending(false);
      resetTurnState();
    }
  }

  function handleInputKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  async function handleDecide(approve: boolean) {
    if (!pendingApproval) return;
    setIsDeciding(true);
    setTurnError(null);
    try {
      if (approve) {
        await approveRequest(pendingApproval.approvalRequestId);
      } else {
        await denyRequest(pendingApproval.approvalRequestId);
      }
      setPendingApproval(null);
      setIsSending(true);
      resetTurnState();
      await resumeTurn(conversationId, handleEvent);
    } catch (err) {
      setTurnError(
        err instanceof ApiRequestError ? err.message : "Couldn't record that decision."
      );
    } finally {
      setIsDeciding(false);
    }
  }

  function autoRunOf(risk: RiskClassification | null): boolean {
    return risk !== null && coworker?.permission_profile[risk] === "auto";
  }

  function resultMessageFor(coworkerMessageId: string, toolCallId: string): ChatMessage | undefined {
    return messages.find(
      (m) => m.parent_message_id === coworkerMessageId && m.tool_call_id === toolCallId
    );
  }

  function renderPersistedToolCall(coworkerMessage: ChatMessage, call: ToolCallRequest) {
    const resultMessage = resultMessageFor(coworkerMessage.id, call.id);
    const isPendingHere =
      !resultMessage &&
      pendingApproval !== null &&
      pendingApproval.messageId === coworkerMessage.id &&
      pendingApproval.toolName === call.name;

    if (isPendingHere) {
      return (
        <ApprovalCard
          key={call.id}
          coworkerName={coworker?.name ?? "Coworker"}
          toolName={call.name}
          args={call.arguments}
          risk={riskOf(toolsByName, call.name)}
          summary={pendingApproval?.summary}
          rationale={pendingApproval?.rationale}
          isDeciding={isDeciding}
          onApprove={() => handleDecide(true)}
          onDeny={() => handleDecide(false)}
          onAlwaysAllow={() => setPolicyDialogOpen(true)}
        />
      );
    }

    let result: Record<string, unknown> | null = null;
    if (resultMessage) {
      try {
        result = JSON.parse(resultMessage.content) as Record<string, unknown>;
      } catch {
        result = { raw: resultMessage.content };
      }
    }

    const risk = riskOf(toolsByName, call.name);
    return (
      <ToolCallCard
        key={call.id}
        toolName={call.name}
        args={call.arguments}
        result={result}
        risk={risk}
        autoRun={autoRunOf(risk)}
        pending={!resultMessage}
      />
    );
  }

  if (isLoading) {
    return (
      <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-4 py-12">
        <p className="text-sm text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (loadError || !conversation || !coworker) {
    return (
      <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-4 px-4 py-12">
        <Alert variant="destructive">
          <AlertDescription>{loadError ?? "Couldn't load this conversation."}</AlertDescription>
        </Alert>
        <Link
          href="/coworkers"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          &larr; Back to coworkers
        </Link>
      </div>
    );
  }

  const isTurnActive = isSending || streamingText.length > 0 || liveToolCalls.length > 0;
  const inputDisabled = isSending || pendingApproval !== null;

  const modelLabel =
    MODEL_SHORT_LABELS[coworker.model_binding.primary] ?? coworker.model_binding.primary;
  const attachedSources = knowledgeBases ?? [];
  const longTermMemories = (memories ?? []).filter((entry) => entry.is_long_term);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 items-stretch gap-8 px-4 py-6">
    <div className="mx-auto flex w-full min-w-0 max-w-2xl flex-1 flex-col">
      <div className="mb-4 flex items-center gap-3 border-b pb-4">
        <Link
          href={`/coworkers/${coworker.id}`}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          aria-label={`Back to ${coworker.name}`}
        >
          <ArrowLeftIcon className="size-3.5" />
        </Link>
        {coworker.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={coworker.avatar_url}
            alt=""
            className="size-9 shrink-0 rounded-full object-cover"
          />
        ) : (
          <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/12 text-primary">
            <BotIcon className="size-4.5" />
          </div>
        )}
        <div className="flex min-w-0 flex-col">
          <div className="flex min-w-0 items-baseline gap-2">
            <span className="truncate font-heading text-sm font-semibold">{coworker.name}</span>
            <span className="hidden truncate text-xs text-muted-foreground sm:inline">
              {coworker.role_description}
            </span>
          </div>
          <span className="truncate text-xs text-muted-foreground">
            {(() => {
              if (pendingApproval) return "Working · paused for your approval";
              if (isTurnActive) return "Working...";
              // Fall back to the server-derived feed: the coworker may be
              // busy elsewhere (a background task) even while this chat idles.
              const feed = statuses.get(coworker.id);
              if (feed && feed.state !== "idle") {
                const label = COWORKER_STATUS_META[feed.state].label;
                return feed.detail ? `${label} · ${feed.detail}` : label;
              }
              return modelLabel;
            })()}
          </span>
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-4 overflow-y-auto pb-4" role="log" aria-label={`Conversation with ${coworker.name}`} aria-live="polite" aria-relevant="additions text">
        {messages
          .filter((m) => m.sender_type !== "system")
          .map((message) => {
            if (message.sender_type === "user") {
              return (
                <div key={message.id} className="flex justify-end">
                  <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl bg-secondary px-4 py-2.5 text-sm text-secondary-foreground">
                    {message.content}
                  </div>
                </div>
              );
            }

            return (
              <div key={message.id} className="flex flex-col gap-2">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  {coworker.avatar_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={coworker.avatar_url}
                      alt=""
                      className="size-4 shrink-0 rounded-full object-cover"
                    />
                  ) : (
                    <BotIcon className="size-4 shrink-0" />
                  )}
                  <span className="font-medium text-foreground">{coworker.name}</span>
                </div>
                {message.content ? (
                  <div className="max-w-full whitespace-pre-wrap pl-6 text-sm leading-relaxed text-foreground">
                    {message.content}
                  </div>
                ) : null}
                <div className="flex flex-col gap-1.5 pl-6">
                  {(message.tool_calls ?? []).map((call) => renderPersistedToolCall(message, call))}
                </div>
              </div>
            );
          })}

        {isTurnActive ? (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              {coworker.avatar_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={coworker.avatar_url}
                  alt=""
                  className="size-4 shrink-0 rounded-full object-cover"
                />
              ) : (
                <BotIcon className="size-4 shrink-0" />
              )}
              <span className="font-medium text-foreground">{coworker.name}</span>
              {!streamingText && liveToolCalls.length === 0 ? (
                <span className="inline-flex items-center gap-1.5 text-muted-foreground">
                  <span className="inline-flex gap-1">
                    <span className="size-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.3s]" />
                    <span className="size-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.15s]" />
                    <span className="size-1.5 animate-bounce rounded-full bg-primary" />
                  </span>
                  Thinking
                </span>
              ) : null}
            </div>
            {streamingText ? (
              <div className="max-w-full whitespace-pre-wrap pl-6 text-sm leading-relaxed text-foreground">
                {streamingText}
              </div>
            ) : null}
            <div className="flex flex-col gap-1.5 pl-6">
            {liveToolCalls.map((tc, i) => {
              const isPendingHere = pendingApproval !== null && tc.result === null;
              const risk = riskOf(toolsByName, tc.toolName);
              if (isPendingHere) {
                return (
                  <ApprovalCard
                    key={i}
                    coworkerName={coworker.name}
                    toolName={tc.toolName}
                    args={tc.arguments ?? {}}
                    risk={risk}
                    summary={pendingApproval?.summary}
                    rationale={pendingApproval?.rationale}
                    isDeciding={isDeciding}
                    onApprove={() => handleDecide(true)}
                    onDeny={() => handleDecide(false)}
                    onAlwaysAllow={() => setPolicyDialogOpen(true)}
                  />
                );
              }
              return (
                <ToolCallCard
                  key={i}
                  toolName={tc.toolName}
                  args={tc.arguments}
                  result={tc.result}
                  risk={risk}
                  autoRun={autoRunOf(risk)}
                  pending={tc.result === null}
                  durationMs={tc.durationMs}
                />
              );
            })}
            </div>
          </div>
        ) : null}

        <div ref={bottomRef} />
      </div>

      {turnError ? (
        <Alert variant="destructive" className="mb-2">
          <AlertDescription>{turnError}</AlertDescription>
        </Alert>
      ) : null}

      <form onSubmit={handleSend} className="pt-2">
        <div className="rounded-2xl border border-border bg-card p-2 shadow-sm transition-colors focus-within:border-primary/50 focus-within:ring-3 focus-within:ring-primary/15">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleInputKeyDown}
            placeholder={
              pendingApproval
                ? "Resolve the pending approval to continue..."
                : `Message ${coworker.name}... (they'll remember this conversation)`
            }
            disabled={inputDisabled}
            rows={1}
            className="max-h-40 min-h-10 w-full resize-none border-0 bg-transparent px-2 py-1.5 shadow-none focus-visible:ring-0"
            aria-label={`Message ${coworker.name}`}
          />
          <div className="flex items-center justify-between gap-2 px-1 pt-1">
            <div className="flex items-center gap-1">
              <Button type="button" size="icon-sm" variant="ghost" disabled={inputDisabled || isListening} onClick={startVoiceInput} aria-pressed={isListening}>
                <span className="sr-only">{isListening ? "Listening" : "Dictate message"}</span><MicIcon />
              </Button>
              <Button type="button" size="icon-sm" variant="ghost" onClick={speakLatestReply} disabled={!messages.some((message) => message.sender_type === "coworker" && message.content)}>
                <span className="sr-only">Read latest coworker reply aloud</span><Volume2Icon />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={inputDisabled || isHandingOff || !input.trim()}
                onClick={handleBackgroundHandoff}
              >
                <ClockIcon data-icon="inline-start" />
                {isHandingOff ? "Queuing..." : "Run in background"}
              </Button>
              <Button type="button" variant="ghost" size="sm" asChild>
                <Link href={`/coworkers/${coworker.id}`} aria-label={`Manage ${coworker.name}'s tools`}>
                  <WrenchIcon data-icon="inline-start" />
                  Tools
                </Link>
              </Button>
            </div>
            <Button type="submit" size="icon" disabled={inputDisabled || !input.trim()}>
              <span className="sr-only">Send message</span>
              <SendIcon />
            </Button>
          </div>
        </div>
      </form>

      {pendingApproval && toolsByName.get(pendingApproval.toolName) ? (
        <ApprovalPolicyDialog
          open={policyDialogOpen}
          onOpenChange={setPolicyDialogOpen}
          workspaceId={conversation.workspace_id}
          coworkerId={coworker.id}
          coworkerName={coworker.name}
          toolId={toolsByName.get(pendingApproval.toolName)!.id}
          toolName={pendingApproval.toolName}
          args={pendingApproval.arguments}
        />
      ) : null}
    </div>

    <aside className="hidden w-72 shrink-0 flex-col gap-4 self-start xl:flex" aria-label="Coworker dossier">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        Dossier
      </p>

      <section className="flex flex-col gap-3 rounded-xl border bg-card p-4">
        <h3 className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          <CpuIcon className="size-3.5" />
          Model
        </h3>
        <div>
          <p className="font-mono text-sm font-semibold">{modelLabel}</p>
          {coworker.model_binding.fallback?.length ? (
            <p className="text-xs text-muted-foreground">
              {coworker.model_binding.fallback.length} fallback
              {coworker.model_binding.fallback.length === 1 ? "" : "s"} configured
            </p>
          ) : null}
        </div>
        <Button size="sm" variant="outline" asChild>
          <Link href={`/coworkers/${coworker.id}`}>Change model</Link>
        </Button>
      </section>

      <section className="flex flex-col gap-3 rounded-xl border bg-card p-4">
        <div className="flex items-center justify-between">
          <h3 className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            <ShieldIcon className="size-3.5" />
            Permissions
          </h3>
          <Link
            href={`/coworkers/${coworker.id}`}
            className="text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            Edit
          </Link>
        </div>
        <ul className="flex flex-col gap-1.5 text-xs">
          {(["safe", "sensitive", "dangerous"] as const).map((tier) => (
            <li key={tier} className="flex items-center justify-between">
              <Badge className={RISK_BADGE_CLASS[tier]}>{RISK_LABELS[tier]}</Badge>
              <span className="text-muted-foreground">
                {coworker.permission_profile[tier] === "auto" ? "Auto-run" : "Ask first"}
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="flex flex-col gap-3 rounded-xl border bg-card p-4">
        <h3 className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          <BrainIcon className="size-3.5" />
          Knowledge &amp; memory
        </h3>
        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-lg border bg-background px-3 py-2">
            <p className="text-lg font-semibold">{memories?.length ?? "—"}</p>
            <p className="text-xs text-muted-foreground">memories</p>
          </div>
          <div className="rounded-lg border bg-background px-3 py-2">
            <p className="text-lg font-semibold">{knowledgeBases ? attachedSources.length : "—"}</p>
            <p className="text-xs text-muted-foreground">sources</p>
          </div>
        </div>
        {attachedSources.length > 0 ? (
          <ul className="flex flex-col gap-1 text-xs">
            {attachedSources.slice(0, 4).map((base) => (
              <li key={base.id} className="truncate text-muted-foreground">
                {base.name}
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      {memories !== null ? (
        <section className="flex flex-col gap-2 rounded-xl border bg-card p-4">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Remembers
          </h3>
          {longTermMemories.length > 0 ? (
            <ul className="flex flex-col gap-2 text-xs leading-relaxed text-muted-foreground">
              {longTermMemories.slice(0, 3).map((entry) => (
                <li key={entry.id} className="line-clamp-3">
                  {entry.content}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-muted-foreground">
              Nothing promoted to long-term memory yet.
            </p>
          )}
        </section>
      ) : null}
    </aside>
    </div>
  );
}
