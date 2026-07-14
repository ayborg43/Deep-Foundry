"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { ArrowLeftIcon, BotIcon, ClockIcon, MicIcon, SendIcon, Volume2Icon, WrenchIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens } from "@/lib/auth";
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
  RiskClassification,
  Tool,
  ToolCallRequest,
} from "@/lib/types";

type LiveToolCall = {
  toolName: string;
  arguments: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
};

type PendingApproval = {
  approvalRequestId: string;
  messageId: string | null;
  toolName: string;
  arguments: Record<string, unknown>;
};

function riskOf(toolsByName: Map<string, Tool>, name: string): RiskClassification | null {
  return toolsByName.get(name)?.risk_classification ?? null;
}

function ToolCallCard({
  toolName,
  args,
  result,
  risk,
  pending,
}: {
  toolName: string;
  args: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  risk: RiskClassification | null;
  pending: boolean;
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
        <span className="font-medium">{toolName}</span>
        {risk ? (
          <Badge className={RISK_BADGE_CLASS[risk]}>{RISK_LABELS[risk]}</Badge>
        ) : null}
        <span className="text-muted-foreground">
          {pending ? "Running..." : "Done"}
        </span>
        <span className="ml-auto text-muted-foreground">
          {expanded ? "Hide" : "Details"}
        </span>
      </button>
      {expanded ? (
        <div id={detailsId} className="flex flex-col gap-2 border-t pt-2">
          {args ? (
            <div>
              <p className="mb-0.5 font-medium text-muted-foreground">Input</p>
              <pre className="overflow-x-auto rounded bg-background p-2">
                {JSON.stringify(args, null, 2)}
              </pre>
            </div>
          ) : null}
          {result ? (
            <div>
              <p className="mb-0.5 font-medium text-muted-foreground">Output</p>
              <pre className="overflow-x-auto rounded bg-background p-2">
                {JSON.stringify(result, null, 2)}
              </pre>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function ApprovalCard({
  toolName,
  args,
  risk,
  isDeciding,
  onApprove,
  onDeny,
}: {
  toolName: string;
  args: Record<string, unknown>;
  risk: RiskClassification | null;
  isDeciding: boolean;
  onApprove: () => void;
  onDeny: () => void;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-amber-500/40 bg-amber-500/5 px-3 py-3 text-sm dark:border-amber-400/30" role="region" aria-label={`Approval required for ${toolName}`}>
      <div className="flex items-center gap-2">
        <WrenchIcon className="size-4 shrink-0 text-amber-600 dark:text-amber-400" />
        <span className="font-medium">Wants to run {toolName}</span>
        {risk ? (
          <Badge className={RISK_BADGE_CLASS[risk]}>{RISK_LABELS[risk]}</Badge>
        ) : null}
      </div>
      <pre className="overflow-x-auto rounded bg-background p-2 text-xs" tabIndex={0} aria-label={`${toolName} arguments`}>
        {JSON.stringify(args, null, 2)}
      </pre>
      <p className="text-xs text-muted-foreground">
        The conversation is paused until you approve or deny this action.
      </p>
      <div className="flex items-center gap-2">
        <Button type="button" size="sm" disabled={isDeciding} onClick={onApprove} aria-label={`Approve ${toolName}`}>
          {isDeciding ? "Working..." : "Approve"}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="destructive"
          disabled={isDeciding}
          onClick={onDeny}
          aria-label={`Deny ${toolName}`}
        >
          Deny
        </Button>
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

        const pending = await listPendingApprovalRequests(conv.workspace_id);
        const mine = pending.find((ar) => ar.conversation_id === conversationId);
        if (mine) {
          setPendingApproval({
            approvalRequestId: mine.id,
            messageId: mine.message_id,
            toolName: mine.tool_name,
            arguments: mine.requested_action.arguments ?? {},
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
        { toolName: event.data.tool_name, arguments: event.data.arguments, result: null },
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
            { toolName: event.data.tool_name, arguments: null, result: event.data.result },
          ];
        }
        const next = [...prev];
        next[idx] = { ...next[idx], result: event.data.result };
        return next;
      });
    } else if (event.event === "approval_required") {
      setPendingApproval({
        approvalRequestId: event.data.approval_request_id,
        messageId: event.data.message_id,
        toolName: event.data.tool_name,
        arguments: event.data.arguments,
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
          toolName={call.name}
          args={call.arguments}
          risk={riskOf(toolsByName, call.name)}
          isDeciding={isDeciding}
          onApprove={() => handleDecide(true)}
          onDeny={() => handleDecide(false)}
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

    return (
      <ToolCallCard
        key={call.id}
        toolName={call.name}
        args={call.arguments}
        result={result}
        risk={riskOf(toolsByName, call.name)}
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

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-4 py-6">
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
          <span className="truncate font-heading text-sm font-semibold">{coworker.name}</span>
          <span className="text-xs text-muted-foreground">
            {MODEL_SHORT_LABELS[coworker.model_binding.primary] ??
              coworker.model_binding.primary}
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
              if (isPendingHere) {
                return (
                  <ApprovalCard
                    key={i}
                    toolName={tc.toolName}
                    args={tc.arguments ?? {}}
                    risk={riskOf(toolsByName, tc.toolName)}
                    isDeciding={isDeciding}
                    onApprove={() => handleDecide(true)}
                    onDeny={() => handleDecide(false)}
                  />
                );
              }
              return (
                <ToolCallCard
                  key={i}
                  toolName={tc.toolName}
                  args={tc.arguments}
                  result={tc.result}
                  risk={riskOf(toolsByName, tc.toolName)}
                  pending={tc.result === null}
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
                : `Message ${coworker.name}...`
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
            </div>
            <Button type="submit" size="icon" disabled={inputDisabled || !input.trim()}>
              <span className="sr-only">Send message</span>
              <SendIcon />
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
}
