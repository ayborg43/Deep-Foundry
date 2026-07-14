"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

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

export default function NewCoworkerPage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [isResolvingWorkspace, setIsResolvingWorkspace] = useState(true);

  const [name, setName] = useState("");
  const [roleDescription, setRoleDescription] = useState("");
  const [primaryModel, setPrimaryModel] =
    useState<ModelId>("deepseek-v4-flash");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getTokens()) {
      router.push("/login");
      return;
    }

    getWorkspaceId()
      .then(setWorkspaceId)
      .finally(() => setIsResolvingWorkspace(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId) return;
    setIsSubmitting(true);
    setError(null);

    try {
      const created = await apiFetch<Coworker>(
        `/workspaces/${workspaceId}/coworkers`,
        {
          method: "POST",
          body: JSON.stringify({
            name,
            role_description: roleDescription,
            model_binding: { primary: primaryModel },
          }),
        }
      );
      router.push(`/coworkers/${created.id}`);
    } catch (err) {
      setError(
        err instanceof ApiRequestError
          ? err.message
          : "Couldn't create the coworker."
      );
      setIsSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-lg flex-1 flex-col justify-center px-4 py-12">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">New coworker</CardTitle>
          <CardDescription>
            Give it a name, a job to do, and a model to think with. You can
            attach tools and adjust everything else afterward.
          </CardDescription>
        </CardHeader>

        {isResolvingWorkspace ? (
          <CardContent>
            <p className="text-sm text-muted-foreground">Loading...</p>
          </CardContent>
        ) : !workspaceId ? (
          <CardContent>
            <Alert variant="destructive">
              <AlertDescription>
                Couldn&apos;t determine your current workspace. Try logging out
                and back in, or sign up again if this is a fresh session.
              </AlertDescription>
            </Alert>
          </CardContent>
        ) : (
          <form onSubmit={handleSubmit}>
            <CardContent className="flex flex-col gap-4">
              {error ? (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              ) : null}

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
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Creating..." : "Create coworker"}
              </Button>
            </CardFooter>
          </form>
        )}
      </Card>
    </div>
  );
}
