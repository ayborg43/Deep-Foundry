"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { PlusIcon, MicIcon, ArrowUpIcon, BellIcon, InboxIcon, Wand2Icon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import { createConversation } from "@/lib/chat";
import type { BackgroundTask, Coworker, User } from "@/lib/types";

const IDEAS = [
  { icon: BellIcon, label: "Send me a daily briefing" },
  { icon: InboxIcon, label: "Organize my knowledge base" },
  { icon: Wand2Icon, label: "Customize a coworker for me" },
];

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Morning";
  if (h < 18) return "Afternoon";
  return "Evening";
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
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!getTokens()) {
      router.push("/login");
      return;
    }
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
      }
    })();
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

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void submit(input);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center px-4 py-16">
      {/* Greeting */}
      <div className="mb-8 flex items-center justify-center gap-3">
        <span aria-hidden className="text-3xl leading-none text-primary">✳</span>
        <h1 className="font-heading text-3xl font-medium tracking-tight sm:text-4xl">
          {greeting()}{name ? `, ${name}` : ""}
        </h1>
      </div>

      {/* Composer */}
      <div className="rounded-2xl border border-border bg-card p-3 shadow-sm transition-colors focus-within:border-primary/40 focus-within:ring-4 focus-within:ring-primary/10">
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
