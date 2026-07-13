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
import type { ProviderCredential } from "@/lib/types";

export default function ProviderCredentialsPage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [credentials, setCredentials] = useState<ProviderCredential[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [label, setLabel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  function loadCredentials(id: string) {
    setIsLoading(true);
    setListError(null);
    apiFetch<ProviderCredential[]>(`/workspaces/${id}/provider-credentials`)
      .then(setCredentials)
      .catch((err) => {
        setListError(
          err instanceof ApiRequestError
            ? err.message
            : "Couldn't load provider credentials."
        );
      })
      .finally(() => setIsLoading(false));
  }

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

      loadCredentials(id);
    }

    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleAdd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId) return;
    setIsSubmitting(true);
    setError(null);

    try {
      const created = await apiFetch<ProviderCredential>(
        `/workspaces/${workspaceId}/provider-credentials`,
        {
          method: "POST",
          body: JSON.stringify({
            label,
            deployment_mode: "deepseek_cloud",
            api_key: apiKey,
            is_default: isDefault,
          }),
        }
      );
      setCredentials((prev) => [...prev, created]);
      setLabel("");
      setApiKey("");
      setIsDefault(false);
    } catch (err) {
      setError(
        err instanceof ApiRequestError
          ? err.message
          : "Couldn't add provider credential."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDelete(credId: string) {
    if (!workspaceId) return;
    setDeletingId(credId);
    setError(null);

    try {
      await apiFetch(`/workspaces/${workspaceId}/provider-credentials/${credId}`, {
        method: "DELETE",
      });
      setCredentials((prev) => prev.filter((c) => c.id !== credId));
    } catch (err) {
      setError(
        err instanceof ApiRequestError
          ? err.message
          : "Couldn't delete provider credential."
      );
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 px-4 py-12">
      <div>
        <h1 className="text-xl font-semibold">Provider credentials</h1>
        <p className="text-sm text-muted-foreground">
          Manage the API keys your workspace uses to call model providers.
        </p>
      </div>

      {!workspaceId && !isLoading ? (
        <Alert variant="destructive">
          <AlertDescription>
            Couldn&apos;t determine your current workspace. Try logging out and
            back in, or sign up again if this is a fresh session.
          </AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Existing credentials</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading...</p>
          ) : listError ? (
            <Alert variant="destructive">
              <AlertDescription>{listError}</AlertDescription>
            </Alert>
          ) : credentials.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No provider credentials yet. Add one below.
            </p>
          ) : (
            <ul className="flex flex-col divide-y">
              {credentials.map((cred) => (
                <li
                  key={cred.id}
                  className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0"
                >
                  <div className="flex flex-col gap-0.5">
                    <span className="text-sm font-medium">
                      {cred.label}
                      {cred.is_default ? (
                        <span className="ml-2 rounded-full bg-secondary px-2 py-0.5 text-xs font-normal text-secondary-foreground">
                          Default
                        </span>
                      ) : null}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {cred.deployment_mode} &middot; {cred.masked_key}
                    </span>
                  </div>
                  <Button
                    type="button"
                    variant="destructive"
                    size="sm"
                    disabled={deletingId === cred.id}
                    onClick={() => handleDelete(cred.id)}
                  >
                    {deletingId === cred.id ? "Removing..." : "Remove"}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {workspaceId ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Add a credential</CardTitle>
            <CardDescription>
              Deployment mode is fixed to DeepSeek Cloud for now.
            </CardDescription>
          </CardHeader>
          <form onSubmit={handleAdd}>
            <CardContent className="flex flex-col gap-4">
              {error ? (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              ) : null}

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="label">Label</Label>
                <Input
                  id="label"
                  type="text"
                  required
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  placeholder="e.g. Production key"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="deployment_mode">Deployment mode</Label>
                <Input id="deployment_mode" type="text" value="deepseek_cloud" disabled />
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="api_key">API key</Label>
                <Input
                  id="api_key"
                  type="password"
                  required
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="sk-..."
                  autoComplete="off"
                />
              </div>

              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={isDefault}
                  onChange={(e) => setIsDefault(e.target.checked)}
                  className="size-4 rounded border-input"
                />
                Set as default
              </label>
            </CardContent>
            <CardFooter>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Adding..." : "Add credential"}
              </Button>
            </CardFooter>
          </form>
        </Card>
      ) : null}
    </div>
  );
}
