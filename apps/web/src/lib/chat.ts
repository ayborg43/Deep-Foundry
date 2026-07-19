// Chat API client — Milestone 4. Plain CRUD (conversations, message
// history, approval decisions) goes through apiFetch like every other
// screen. Sending/resuming a turn is different: those endpoints stream
// Server-Sent Events on the same HTTP response (API.md §4), which apiFetch
// can't handle (it reads the whole body and JSON-parses it) — streamTurn
// below is a parallel, minimal SSE reader instead of a fetch wrapper.

import { API_BASE_URL, apiFetch, ApiRequestError } from "./api";
import { getTokens } from "./auth";
import type {
  ApprovalRequestData,
  ChatMessage,
  Conversation,
} from "./types";

export type ChatSSEEvent =
  | { event: "token"; data: { delta: string } }
  | {
      event: "tool_call_started";
      data: { tool_name: string; arguments: Record<string, unknown>; message_id: string };
    }
  | {
      event: "tool_call_result";
      data: { tool_name: string; result: Record<string, unknown>; message_id: string };
    }
  | {
      event: "approval_required";
      data: {
        approval_request_id: string;
        tool_name: string;
        arguments: Record<string, unknown>;
        message_id: string;
        summary?: string;
        rationale?: string;
      };
    }
  | { event: "message_complete"; data: { content: string } }
  | { event: "error"; data: { detail: string } };

async function streamTurn(
  path: string,
  options: RequestInit,
  onEvent: (event: ChatSSEEvent) => void
): Promise<void> {
  const tokens = getTokens();
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  if (tokens?.access) {
    headers.set("Authorization", `Bearer ${tokens.access}`);
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/v1${path}`, { ...options, headers });
  } catch {
    throw new ApiRequestError(
      0,
      "network_error",
      "Couldn't reach the server. Check your connection and try again."
    );
  }

  if (!res.ok || !res.body) {
    const raw = await res.text();
    const data = raw ? (JSON.parse(raw) as { error?: { code?: string; message?: string } }) : {};
    throw new ApiRequestError(
      res.status,
      data.error?.code ?? "unknown_error",
      data.error?.message ?? "Something went wrong. Please try again."
    );
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      if (!block.trim()) continue;
      let eventName: string | null = null;
      let dataLine: string | null = null;
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) eventName = line.slice("event: ".length);
        else if (line.startsWith("data: ")) dataLine = line.slice("data: ".length);
      }
      if (eventName && dataLine) {
        onEvent({ event: eventName, data: JSON.parse(dataLine) } as ChatSSEEvent);
      }
    }
  }
}

export function createConversation(
  workspaceId: string,
  coworkerId: string,
  title?: string
): Promise<Conversation> {
  return apiFetch<Conversation>("/conversations", {
    method: "POST",
    body: JSON.stringify({
      workspace_id: workspaceId,
      coworker_id: coworkerId,
      ...(title ? { title } : {}),
    }),
  });
}

export function getConversation(conversationId: string): Promise<Conversation> {
  return apiFetch<Conversation>(`/conversations/${conversationId}`);
}

export function listMessages(conversationId: string): Promise<ChatMessage[]> {
  return apiFetch<ChatMessage[]>(`/conversations/${conversationId}/messages`);
}

// Pending approval requests for a workspace — used on chat page load to
// recover "this conversation is paused on an approval" state after a
// reload, since that isn't otherwise reflected in the message history.
export function listPendingApprovalRequests(
  workspaceId: string
): Promise<ApprovalRequestData[]> {
  return apiFetch<ApprovalRequestData[]>(
    `/workspaces/${workspaceId}/approval-requests?status=pending`
  );
}

export function approveRequest(approvalRequestId: string): Promise<ApprovalRequestData> {
  return apiFetch<ApprovalRequestData>(`/approval-requests/${approvalRequestId}/approve`, {
    method: "POST",
  });
}

export function denyRequest(approvalRequestId: string): Promise<ApprovalRequestData> {
  return apiFetch<ApprovalRequestData>(`/approval-requests/${approvalRequestId}/deny`, {
    method: "POST",
  });
}

export function sendMessage(
  conversationId: string,
  content: string,
  onEvent: (event: ChatSSEEvent) => void
): Promise<void> {
  return streamTurn(
    `/conversations/${conversationId}/messages`,
    { method: "POST", body: JSON.stringify({ content }) },
    onEvent
  );
}

export function resumeTurn(
  conversationId: string,
  onEvent: (event: ChatSSEEvent) => void
): Promise<void> {
  return streamTurn(`/conversations/${conversationId}/messages/stream`, { method: "GET" }, onEvent);
}
