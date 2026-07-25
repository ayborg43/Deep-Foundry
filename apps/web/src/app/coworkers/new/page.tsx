"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { CheckIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import { createConversation } from "@/lib/chat";
import { MODEL_OPTIONS, RISK_BADGE_CLASS, RISK_LABELS } from "@/lib/coworkers";
import type { Coworker, ModelId, Tool } from "@/lib/types";

export default function HireCoworkerPage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [isResolvingWorkspace, setIsResolvingWorkspace] = useState(true);
  const [name, setName] = useState("");
  const [roleDescription, setRoleDescription] = useState("");
  const [primaryModel, setPrimaryModel] =
    useState<ModelId>("deepseek-v4-flash");
  const [tools, setTools] = useState<Tool[]>([]);
  const [selectedToolIds, setSelectedToolIds] = useState<Set<string>>(new Set());
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getTokens()) {
      router.push("/login");
      return;
    }

    getWorkspaceId()
      .then(setWorkspaceId)
      .finally(() => setIsResolvingWorkspace(false));

    // Pre-select the safe tools so a new coworker can do something useful from
    // the first message; the person can trim or add higher-risk tools here or
    // later on the coworker's page.
    void apiFetch<Tool[]>("/tools")
      .then((all) => {
        setTools(all);
        setSelectedToolIds(
          new Set(all.filter((t) => t.risk_classification === "safe").map((t) => t.id))
        );
      })
      .catch(() => {
        // The picker just stays empty; tools can still be added afterward.
      });

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggleTool(id: string) {
    setSelectedToolIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function hire(
    coworkerName: string,
    role: string,
    model: ModelId,
    busy: string
  ) {
    if (!workspaceId) return;
    setBusyKey(busy);
    setError(null);
    try {
      const created = await apiFetch<Coworker>(
        `/workspaces/${workspaceId}/coworkers`,
        {
          method: "POST",
          body: JSON.stringify({
            name: coworkerName,
            role_description: role,
            model_binding: { primary: model },
          }),
        }
      );
      // Attach the chosen tools before the first turn so the coworker can
      // actually act on what it's asked. Individual failures are tolerated —
      // any tool that didn't attach can be added later on its page.
      if (selectedToolIds.size > 0) {
        await Promise.allSettled(
          [...selectedToolIds].map((toolId) =>
            apiFetch(`/coworkers/${created.id}/tools`, {
              method: "POST",
              body: JSON.stringify({ tool_id: toolId }),
            })
          )
        );
      }
      // Drop straight into a chat where the coworker introduces itself and asks
      // its setup questions, which you answer inline. The ?onboard=1 flag tells
      // the conversation page to fire that coworker-first opening turn.
      try {
        const conversation = await createConversation(
          workspaceId,
          created.id,
          `Getting started with ${created.name}`
        );
        router.push(`/conversations/${conversation.id}?onboard=1`);
      } catch {
        // If the conversation can't be created, the coworker still exists —
        // fall back to its profile so the hire isn't lost.
        router.push(`/coworkers/${created.id}`);
      }
    } catch (err) {
      setError(
        err instanceof ApiRequestError
          ? err.message
          : "Couldn't hire this coworker."
      );
      setBusyKey(null);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void hire(name, roleDescription, primaryModel, "custom");
  }

  if (isResolvingWorkspace) {
    return (
      <div className="mx-auto w-full max-w-4xl px-4 py-12">
        <p className="text-sm text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (!workspaceId) {
    return (
      <div className="mx-auto w-full max-w-lg px-4 py-12">
        <Alert variant="destructive">
          <AlertDescription>
            Couldn&apos;t determine your current workspace. Try logging out
            and back in, or sign up again if this is a fresh session.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-4 py-10 sm:px-6">
      <header>
        <h1 className="font-heading text-2xl font-semibold tracking-tight">
          Hire a coworker
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Describe the job and configure your new coworker.
        </p>
      </header>

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      <section aria-label="Create your own" className="flex flex-col gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Create a coworker
        </h2>
        <Card className="max-w-lg">
          <form onSubmit={handleSubmit}>
            <CardHeader>
              <CardDescription>
                Give it a name, a job to do, and a model to think with. You
                can attach tools, upload an avatar, and adjust everything
                else afterward.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="name">Name</Label>
                <Input
                  id="name"
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Ava"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="role_description">Role description</Label>
                <Textarea
                  id="role_description"
                  required
                  value={roleDescription}
                  onChange={(e) => setRoleDescription(e.target.value)}
                  placeholder="What is this coworker responsible for?"
                  rows={4}
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="model">Model</Label>
                <Select
                  value={primaryModel}
                  onValueChange={(value) => setPrimaryModel(value as ModelId)}
                >
                  <SelectTrigger id="model" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {MODEL_OPTIONS.map((option) => (
                      <SelectItem key={option.id} value={option.id}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {MODEL_OPTIONS.find((option) => option.id === primaryModel)
                    ?.description ?? "Choose the model this coworker will use."}
                </p>
              </div>

              {tools.length > 0 ? (
                <div className="flex flex-col gap-1.5">
                  <Label>Tools</Label>
                  <p className="text-xs text-muted-foreground">
                    Safe tools are pre-selected so {name.trim() || "your coworker"} can
                    help right away. Sensitive and dangerous tools still ask for your
                    approval before running.
                  </p>
                  <ul className="mt-1 flex flex-col divide-y rounded-lg border">
                    {tools.map((tool) => {
                      const checked = selectedToolIds.has(tool.id);
                      return (
                        <li key={tool.id}>
                          <button
                            type="button"
                            onClick={() => toggleTool(tool.id)}
                            aria-pressed={checked}
                            className="flex w-full items-start gap-3 px-3 py-2.5 text-left transition-colors hover:bg-accent/40"
                          >
                            <span
                              className={`mt-0.5 flex size-4 shrink-0 items-center justify-center rounded border ${
                                checked
                                  ? "border-primary bg-primary text-primary-foreground"
                                  : "border-input"
                              }`}
                            >
                              {checked ? <CheckIcon className="size-3" /> : null}
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="flex items-center gap-2">
                                <span className="text-sm font-medium">{tool.name}</span>
                                <Badge className={RISK_BADGE_CLASS[tool.risk_classification]}>
                                  {RISK_LABELS[tool.risk_classification]}
                                </Badge>
                              </span>
                              <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                                {tool.description}
                              </span>
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ) : null}
            </CardContent>
            <CardFooter>
              <Button type="submit" disabled={busyKey !== null}>
                {busyKey === "custom" ? "Hiring..." : "Hire coworker"}
              </Button>
            </CardFooter>
          </form>
        </Card>
      </section>
    </div>
  );
}
