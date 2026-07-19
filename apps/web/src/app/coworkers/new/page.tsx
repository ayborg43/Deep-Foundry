"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { BotIcon, PlusIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
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
import { MODEL_OPTIONS } from "@/lib/coworkers";
import type { Coworker, ModelId } from "@/lib/types";

type TeamTemplate = {
  key: string;
  label: string;
  description: string;
  coworkers: { name: string; role_description: string }[];
};

type CoworkerTemplate = {
  templateKey: string;
  templateLabel: string;
  name: string;
  role_description: string;
};

export default function HireCoworkerPage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [isResolvingWorkspace, setIsResolvingWorkspace] = useState(true);
  const [templates, setTemplates] = useState<CoworkerTemplate[]>([]);

  const [name, setName] = useState("");
  const [roleDescription, setRoleDescription] = useState("");
  const [primaryModel, setPrimaryModel] =
    useState<ModelId>("deepseek-v4-flash");
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

    // Ready-made roles configured on this instance. Failure just hides
    // the gallery; the create-your-own form always works.
    void apiFetch<TeamTemplate[]>("/team-templates")
      .then((catalog) =>
        setTemplates(
          catalog.flatMap((template) =>
            template.coworkers.map((member) => ({
              templateKey: template.key,
              templateLabel: template.label,
              name: member.name,
              role_description: member.role_description,
            }))
          )
        )
      )
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
      router.push(`/coworkers/${created.id}`);
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
          Pick a ready-made role, or describe the job yourself.
        </p>
      </header>

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}

      {templates.length > 0 ? (
        <section aria-label="Ready-made roles" className="flex flex-col gap-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Ready-made roles
          </h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {templates.map((template) => {
              const key = `${template.templateKey}:${template.name}`;
              return (
                <Card key={key} className="flex flex-col">
                  <CardHeader className="flex-row items-center gap-3">
                    <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/12 text-primary">
                      <BotIcon className="size-4.5" />
                    </div>
                    <div className="min-w-0">
                      <CardTitle className="truncate text-base">
                        {template.name}
                      </CardTitle>
                      <p className="text-xs text-muted-foreground">
                        {template.templateLabel}
                      </p>
                    </div>
                  </CardHeader>
                  <CardContent className="flex flex-1 flex-col gap-3">
                    <p className="line-clamp-3 flex-1 text-sm text-muted-foreground">
                      {template.role_description}
                    </p>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busyKey !== null}
                      onClick={() =>
                        void hire(
                          template.name,
                          template.role_description,
                          "deepseek-v4-flash",
                          key
                        )
                      }
                    >
                      <PlusIcon data-icon="inline-start" />
                      {busyKey === key ? "Hiring..." : "Hire"}
                    </Button>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </section>
      ) : null}

      <section aria-label="Create your own" className="flex flex-col gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {templates.length > 0 ? "Or create your own" : "Create a coworker"}
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
