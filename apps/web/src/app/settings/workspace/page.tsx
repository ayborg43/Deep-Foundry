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
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import type { Workspace } from "@/lib/types";

export default function WorkspaceSettingsPage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!getTokens()) {
      router.push("/login");
      return;
    }

    // Reads localStorage, falling back to GET /workspaces — only
    // resolvable post-mount, and the page has nothing meaningful to
    // render without it, so we resolve it once here rather than introduce
    // a store subscription for a value that never changes for the life of
    // the session.
    async function load() {
      const id = await getWorkspaceId();
      setWorkspaceId(id);

      if (!id) {
        setIsLoading(false);
        return;
      }

      apiFetch<Workspace>(`/workspaces/${id}`)
        .then((data) => {
          setWorkspace(data);
          setName(data.name);
        })
        .catch((err) => {
          setError(
            err instanceof ApiRequestError
              ? err.message
              : "Couldn't load workspace details."
          );
        })
        .finally(() => setIsLoading(false));
    }

    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId) return;
    setIsSaving(true);
    setError(null);
    setSaved(false);

    try {
      const updated = await apiFetch<Workspace>(`/workspaces/${workspaceId}`, {
        method: "PATCH",
        body: JSON.stringify({ name }),
      });
      setWorkspace(updated);
      setName(updated.name);
      setSaved(true);
    } catch (err) {
      setError(
        err instanceof ApiRequestError
          ? err.message
          : "Couldn't save workspace changes."
      );
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-lg flex-1 flex-col justify-center px-4 py-12">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Workspace settings</CardTitle>
          <CardDescription>
            Manage your workspace&apos;s basic details.
          </CardDescription>
        </CardHeader>

        {isLoading ? (
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
              {saved ? (
                <Alert>
                  <AlertDescription>Workspace updated.</AlertDescription>
                </Alert>
              ) : null}

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="name">Workspace name</Label>
                <Input
                  id="name"
                  type="text"
                  required
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    setSaved(false);
                  }}
                />
              </div>

              {workspace ? (
                <dl className="grid grid-cols-2 gap-y-1 text-sm text-muted-foreground">
                  <dt>Type</dt>
                  <dd className="text-foreground">{workspace.type}</dd>
                  <dt>Plan</dt>
                  <dd className="text-foreground">{workspace.plan_tier}</dd>
                </dl>
              ) : null}
            </CardContent>
            <CardFooter>
              <Button type="submit" disabled={isSaving}>
                {isSaving ? "Saving..." : "Save changes"}
              </Button>
            </CardFooter>
          </form>
        )}
      </Card>
    </div>
  );
}
