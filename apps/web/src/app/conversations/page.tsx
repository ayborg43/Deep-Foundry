"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { MessageSquareIcon, PlusIcon, Trash2Icon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import { deleteConversation } from "@/lib/chat";
import type { Conversation } from "@/lib/types";

export default function ConversationsPage() {
  const router = useRouter();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function handleDelete(conversation: Conversation) {
    if (!window.confirm(`Delete "${conversation.title || "Untitled conversation"}"? Its messages are removed permanently.`)) return;
    setDeletingId(conversation.id);
    setError(null);
    try {
      await deleteConversation(conversation.id);
      setConversations((current) => current.filter((c) => c.id !== conversation.id));
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn't delete that conversation.");
    } finally {
      setDeletingId(null);
    }
  }

  useEffect(() => {
    if (!getTokens()) {
      router.push("/login");
      return;
    }
    void (async () => {
      const workspace = await getWorkspaceId();
      if (!workspace) {
        setLoading(false);
        return;
      }
      try {
        setConversations(await apiFetch<Conversation[]>(`/conversations?workspace_id=${workspace}`));
      } catch (err) {
        setError(err instanceof ApiRequestError ? err.message : "Couldn't load conversations.");
      } finally {
        setLoading(false);
      }
    })();
  }, [router]);

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-4 py-10 sm:px-6">
      <PageHeader
        title="Conversations"
        description="Your interactive, streaming chats with coworkers. Open one to pick up where you left off."
        actions={
          <Button asChild size="sm">
            <Link href="/home">
              <PlusIcon data-icon="inline-start" />
              New conversation
            </Link>
          </Button>
        }
      />

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {loading ? (
        <div className="flex flex-col gap-2.5" aria-hidden>
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-16 animate-pulse rounded-xl border border-border bg-card" />
          ))}
        </div>
      ) : conversations.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
            <span className="flex size-11 items-center justify-center rounded-full bg-secondary text-muted-foreground">
              <MessageSquareIcon className="size-5" />
            </span>
            <div>
              <p className="text-sm font-medium">No conversations yet</p>
              <p className="mt-0.5 text-sm text-muted-foreground">
                Start a chat with a coworker and it will show up here.
              </p>
            </div>
            <Button asChild size="sm" className="mt-1">
              <Link href="/home">
                <PlusIcon data-icon="inline-start" />
                New conversation
              </Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <ul className="flex flex-col gap-2.5">
          {conversations.map((conversation) => (
            <li key={conversation.id}>
              <Link href={`/conversations/${conversation.id}`} className="group/row block">
                <Card className="transition-all group-hover/row:border-primary/40 group-hover/row:shadow-[var(--shadow-sm)]">
                  <CardContent className="flex items-center gap-3 py-3.5">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-secondary text-muted-foreground transition-colors group-hover/row:text-foreground">
                      <MessageSquareIcon className="size-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">
                        {conversation.title || "Untitled conversation"}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {new Date(conversation.created_at).toLocaleString()}
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      disabled={deletingId === conversation.id}
                      aria-label={`Delete conversation ${conversation.title || "Untitled conversation"}`}
                      className="shrink-0 text-muted-foreground opacity-0 transition-opacity hover:text-destructive focus-visible:opacity-100 group-hover/row:opacity-100"
                      onClick={(event) => {
                        event.preventDefault();
                        void handleDelete(conversation);
                      }}
                    >
                      <Trash2Icon />
                    </Button>
                  </CardContent>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
