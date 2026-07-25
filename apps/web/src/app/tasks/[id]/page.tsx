"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { MessageCircleQuestionIcon } from "lucide-react";

import { FormattedMessage } from "@/components/formatted-message";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { StatusBadge } from "@/components/status-badge";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens } from "@/lib/auth";
import type { BackgroundTask } from "@/lib/types";

export default function TaskDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [task, setTask] = useState<BackgroundTask | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState("");
  const [respondBusy, setRespondBusy] = useState(false);

  async function load() {
    try { setTask(await apiFetch<BackgroundTask>(`/tasks/${id}`)); }
    catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn't load task."); }
  }

  useEffect(() => {
    if (!getTokens()) { router.push("/login"); return; }
    const initial = window.setTimeout(() => void load(), 0);
    const timer = window.setInterval(load, 5_000);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, router]);

  async function decide(approve: boolean) {
    setBusy(true); setError(null);
    try { await apiFetch(`/tasks/${id}/${approve ? "approve" : "deny"}`, { method: "POST" }); await load(); }
    catch (err) { setError(err instanceof ApiRequestError ? err.message : "Couldn't record decision."); }
    finally { setBusy(false); }
  }

  async function respond(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = answer.trim();
    if (!content) return;
    setRespondBusy(true); setError(null);
    try {
      const updated = await apiFetch<BackgroundTask>(`/tasks/${id}/respond`, {
        method: "POST",
        body: JSON.stringify({ content }),
      });
      setTask(updated);
      setAnswer("");
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn't send your reply.");
    } finally {
      setRespondBusy(false);
    }
  }

  if (!task) return <div className="mx-auto w-full max-w-3xl px-4 py-12"><p className="text-sm text-muted-foreground">Loading...</p></div>;
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-5 px-4 py-10 sm:px-6">
      <Link href="/tasks" className="text-sm text-muted-foreground hover:text-foreground">&larr; All tasks</Link>
      {error ? <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert> : null}
      <div className="flex items-start justify-between gap-4"><div><h1 className="font-heading text-2xl font-semibold tracking-tight">{task.title}</h1><p className="text-sm text-muted-foreground">Assigned to {task.coworker_name}</p></div><StatusBadge status={task.status} /></div>

      {task.status === "needs_input" ? (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-4 dark:border-amber-400/30">
          <div className="flex items-start gap-3">
            <MessageCircleQuestionIcon className="mt-0.5 size-5 shrink-0 text-amber-600 dark:text-amber-400" />
            <div className="min-w-0 flex-1">
              <p className="font-medium">{task.coworker_name} has a question</p>
              <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed">
                {task.pending_question ?? "This coworker paused and is waiting for your input to continue."}
              </p>
              <form onSubmit={respond} className="mt-3 flex flex-col gap-2">
                <Textarea
                  value={answer}
                  onChange={(event) => setAnswer(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      event.currentTarget.form?.requestSubmit();
                    }
                  }}
                  rows={2}
                  placeholder="Type your answer — the task resumes as soon as you reply…"
                  aria-label="Your answer"
                  className="bg-background"
                />
                <Button type="submit" size="sm" className="w-fit" disabled={respondBusy || !answer.trim()}>
                  {respondBusy ? "Sending…" : "Send & resume"}
                </Button>
              </form>
            </div>
          </div>
        </div>
      ) : null}

      {task.status === "needs_approval" ? <div className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-4 dark:border-amber-400/30"><div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><p className="font-medium">Approval needed to continue</p><p className="text-sm text-muted-foreground">This coworker has shared its plan and paused. It won&apos;t act until you approve.</p></div><span className="flex shrink-0 gap-2"><Button size="sm" disabled={busy} onClick={() => void decide(true)}>Approve</Button><Button size="sm" variant="destructive" disabled={busy} onClick={() => void decide(false)}>Deny</Button></span></div></div> : null}
      <Card><CardHeader><CardTitle className="font-heading text-lg">Instructions</CardTitle></CardHeader><CardContent><p className="whitespace-pre-wrap text-sm leading-relaxed">{task.description}</p></CardContent></Card>
      {task.result ? <Card><CardHeader><CardTitle className="font-heading text-lg">Result</CardTitle></CardHeader><CardContent><FormattedMessage content={task.result} /></CardContent></Card> : null}
      {task.error_message ? <Alert variant="destructive"><AlertDescription>{task.error_message}</AlertDescription></Alert> : null}
      <p className="text-xs text-muted-foreground">Created {new Date(task.created_at).toLocaleString()} · Updated {new Date(task.updated_at).toLocaleString()}</p>
    </div>
  );
}
