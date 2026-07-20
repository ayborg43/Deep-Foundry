"use client";

import { QRCodeSVG } from "qrcode.react";
import {
  BellIcon,
  CheckCircle2Icon,
  ExternalLinkIcon,
  LockKeyholeIcon,
  MessageCircleIcon,
  SendIcon,
  UnplugIcon,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { apiFetch } from "@/lib/api";
import { getWorkspaceId } from "@/lib/auth";
import type {
  TelegramConnection,
  TelegramLinkSession,
  TelegramNotificationPreferences,
} from "@/lib/types";

const preferenceRows: {
  key: Exclude<keyof TelegramNotificationPreferences, "workspace_id">;
  label: string;
  description: string;
}[] = [
  {
    key: "enabled",
    label: "Telegram notifications",
    description: "Pause or resume all Telegram alerts for this workspace.",
  },
  {
    key: "task_completed",
    label: "Task completed",
    description: "When a coworker finishes a background task.",
  },
  {
    key: "research_completed",
    label: "Research completed",
    description: "When a Deep Research report is ready.",
  },
  {
    key: "website_changed",
    label: "Website changed",
    description: "When a monitored website has a meaningful update.",
  },
  {
    key: "approval_requested",
    label: "Approval required",
    description: "When a coworker is waiting for your decision.",
  },
  {
    key: "task_failed",
    label: "Task or workflow needs attention",
    description: "When execution fails or becomes blocked.",
  },
  {
    key: "monitor_failed",
    label: "Website monitor failed",
    description: "When a scheduled website check cannot finish.",
  },
];

export default function NotificationSettingsPage() {
  const [workspaceId, setWorkspaceId] = useState("");
  const [connection, setConnection] = useState<TelegramConnection | null>(null);
  const [preferences, setPreferences] =
    useState<TelegramNotificationPreferences | null>(null);
  const [linkSession, setLinkSession] = useState<TelegramLinkSession | null>(null);
  const [linkOpen, setLinkOpen] = useState(false);
  const [disconnectOpen, setDisconnectOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async (id: string) => {
    const [nextConnection, nextPreferences] = await Promise.all([
      apiFetch<TelegramConnection>("/telegram/connection"),
      apiFetch<TelegramNotificationPreferences>(
        `/telegram/preferences?workspace_id=${encodeURIComponent(id)}`,
      ),
    ]);
    setConnection(nextConnection);
    setPreferences(nextPreferences);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const id = await getWorkspaceId();
        if (!id) throw new Error("Choose a workspace to configure notifications.");
        if (cancelled) return;
        setWorkspaceId(id);
        await load(id);
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : "Could not load notifications.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  useEffect(() => {
    if (!linkOpen || linkSession?.status !== "pending") return;
    let cancelled = false;
    const poll = window.setInterval(() => {
      void (async () => {
        try {
          const next = await apiFetch<TelegramLinkSession>(
            `/telegram/link-sessions/${linkSession.id}`,
          );
          if (cancelled) return;
          setLinkSession((current) => ({ ...current, ...next }));
          if (next.status === "linked") {
            window.clearInterval(poll);
            await load(workspaceId);
            if (!cancelled) {
              setNotice("Telegram is connected.");
              setLinkOpen(false);
            }
          }
        } catch {
          // Keep the dialog usable; a transient poll failure can recover.
        }
      })();
    }, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(poll);
    };
  }, [linkOpen, linkSession?.id, linkSession?.status, load, workspaceId]);

  useEffect(() => {
    const refresh = () => {
      if (workspaceId && linkSession?.status === "pending") {
        void apiFetch<TelegramLinkSession>(
          `/telegram/link-sessions/${linkSession.id}`,
        ).then((next) => setLinkSession((current) => ({ ...current, ...next })));
      }
    };
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [linkSession?.id, linkSession?.status, workspaceId]);

  async function connect() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const session = await apiFetch<TelegramLinkSession>("/telegram/link-sessions", {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspaceId }),
      });
      setLinkSession(session);
      setLinkOpen(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not start Telegram linking.");
    } finally {
      setBusy(false);
    }
  }

  async function savePreferences() {
    if (!preferences) return;
    setBusy(true);
    setError("");
    setNotice("");
    const values = Object.fromEntries(
      preferenceRows.map(({ key }) => [key, preferences[key]]),
    );
    try {
      const saved = await apiFetch<TelegramNotificationPreferences>(
        `/telegram/preferences?workspace_id=${encodeURIComponent(workspaceId)}`,
        { method: "PATCH", body: JSON.stringify(values) },
      );
      setPreferences(saved);
      setNotice("Telegram notification preferences saved.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save preferences.");
    } finally {
      setBusy(false);
    }
  }

  async function sendTest() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await apiFetch("/telegram/test", {
        method: "POST",
        body: JSON.stringify({ workspace_id: workspaceId }),
      });
      setNotice("A Telegram test notification has been queued.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not send the test.");
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    setBusy(true);
    setError("");
    try {
      await apiFetch("/telegram/connection", { method: "DELETE" });
      await load(workspaceId);
      setLinkSession(null);
      setDisconnectOpen(false);
      setNotice("Telegram has been disconnected.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not disconnect Telegram.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <main className="mx-auto w-full max-w-4xl px-4 py-10">
        <p className="text-sm text-muted-foreground">Loading notification settings…</p>
      </main>
    );
  }

  const connectedLabel =
    connection?.username
      ? `@${connection.username}`
      : connection?.display_name || "Telegram account";

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-4 py-10">
      <header className="space-y-1">
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <BellIcon className="size-6" />
          Notifications
        </h1>
        <p className="text-sm text-muted-foreground">
          Choose how Deep Foundry tells you when work needs attention or is complete.
        </p>
      </header>

      <div aria-live="polite" className="space-y-3">
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {notice && (
          <Alert>
            <CheckCircle2Icon />
            <AlertDescription>{notice}</AlertDescription>
          </Alert>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.05fr_0.95fr]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <MessageCircleIcon className="size-5" />
              Telegram
            </CardTitle>
            <CardDescription>
              Connect a private chat. You will never be asked for a phone number or chat ID.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {!connection?.available ? (
              <Alert>
                <AlertDescription>
                  Telegram is not configured on this Deep Foundry deployment. An operator
                  must add the bot credentials before users can connect.
                </AlertDescription>
              </Alert>
            ) : connection.connected ? (
              <>
                <div className="rounded-lg border bg-muted/40 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="font-medium">{connectedLabel}</p>
                      <p className="text-xs text-muted-foreground">
                        Connected{" "}
                        {connection.connected_at
                          ? new Date(connection.connected_at).toLocaleString()
                          : "to Telegram"}
                      </p>
                    </div>
                    <Badge variant="secondary">Connected</Badge>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    className="min-h-11"
                    variant="outline"
                    onClick={sendTest}
                    disabled={busy}
                  >
                    <SendIcon data-icon="inline-start" />
                    Send test
                  </Button>
                  <Button
                    className="min-h-11"
                    variant="outline"
                    onClick={() => setDisconnectOpen(true)}
                    disabled={busy}
                  >
                    <UnplugIcon data-icon="inline-start" />
                    Disconnect
                  </Button>
                </div>
              </>
            ) : (
              <div className="space-y-4">
                <p className="text-sm text-muted-foreground">
                  Deep Foundry creates a one-time link. Tap Start in Telegram and your
                  account is connected automatically.
                </p>
                <Button className="min-h-11" onClick={connect} disabled={busy || !workspaceId}>
                  <MessageCircleIcon data-icon="inline-start" />
                  Connect Telegram
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <LockKeyholeIcon className="size-5" />
              Private by default
            </CardTitle>
            <CardDescription>
              Telegram alerts are intentionally brief.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <p>
              Messages contain the event type, a short title, and a secure link back to
              Deep Foundry.
            </p>
            <p>
              Task results, prompts, research evidence, monitored page contents, and
              error details are not copied into Telegram.
            </p>
            <p>
              Connections belong to your user account. Each workspace has its own alert
              choices.
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Workspace alerts</CardTitle>
          <CardDescription>
            Select the events you want for the active workspace.
          </CardDescription>
        </CardHeader>
        <CardContent className="divide-y">
          {preferences &&
            preferenceRows.map((row) => {
              const id = `telegram-${row.key}`;
              return (
                <div
                  key={row.key}
                  className="flex min-h-16 items-center justify-between gap-5 py-4 first:pt-0 last:pb-0"
                >
                  <div className="min-w-0">
                    <Label htmlFor={id} className="font-medium">
                      {row.label}
                    </Label>
                    <p className="mt-1 text-sm text-muted-foreground">{row.description}</p>
                  </div>
                  <Switch
                    id={id}
                    checked={preferences[row.key]}
                    disabled={!connection?.connected || busy}
                    onCheckedChange={(checked) =>
                      setPreferences((current) =>
                        current ? { ...current, [row.key]: checked } : current,
                      )
                    }
                  />
                </div>
              );
            })}
          <div className="pt-5">
            <Button
              className="min-h-11"
              disabled={!connection?.connected || !preferences || busy}
              onClick={savePreferences}
            >
              Save preferences
            </Button>
          </div>
        </CardContent>
      </Card>

      <Dialog open={linkOpen} onOpenChange={setLinkOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Connect Telegram</DialogTitle>
            <DialogDescription>
              Open the one-time link, tap Start in the private bot chat, then return
              here. This dialog will update automatically.
            </DialogDescription>
          </DialogHeader>
          {linkSession?.deep_link_url && (
            <div className="flex flex-col items-center gap-4">
              <div
                className="rounded-xl bg-white p-3"
                role="img"
                aria-label="Telegram connection QR code"
              >
                <QRCodeSVG value={linkSession.deep_link_url} size={180} />
              </div>
              <Button asChild className="min-h-11 w-full">
                <a
                  href={linkSession.deep_link_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Open @{connection?.bot_username || "Telegram bot"}
                  <ExternalLinkIcon data-icon="inline-end" />
                </a>
              </Button>
            </div>
          )}
          <div className="rounded-lg border bg-muted/40 p-3 text-sm" aria-live="polite">
            {linkSession?.status === "pending" && "Waiting for you to tap Start in Telegram…"}
            {linkSession?.status === "expired" && "This link expired. Close and create a new link."}
            {linkSession?.status === "cancelled" && "This link was cancelled. Create a new link."}
            {linkSession?.status === "linked" && "Telegram is connected."}
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">Close</Button>
            </DialogClose>
            {(linkSession?.status === "expired" || linkSession?.status === "cancelled") && (
              <Button onClick={connect} disabled={busy}>
                Create new link
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={disconnectOpen} onOpenChange={setDisconnectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Disconnect Telegram?</DialogTitle>
            <DialogDescription>
              Deep Foundry will stop sending Telegram alerts and remove your
              workspace alert preferences. You can reconnect later.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button variant="destructive" onClick={disconnect} disabled={busy}>
              Disconnect
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
