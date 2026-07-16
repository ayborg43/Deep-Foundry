"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { ArrowLeftIcon, BotIcon, MessageCircleIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import { createConversation } from "@/lib/chat";
import {
  MODEL_LABELS,
  MODEL_OPTIONS,
  RISK_BADGE_CLASS,
  RISK_LABELS,
} from "@/lib/coworkers";
import type {
  Coworker,
  CoworkerToolAttachment,
  CoworkerVersion,
  ModelBinding,
  ModelId,
  PermissionProfile,
  Tool,
} from "@/lib/types";

const RISK_LEVELS = ["safe", "sensitive", "dangerous"] as const;

type IdentitySnapshot = {
  name: string;
  avatarUrl: string;
  roleDescription: string;
  modelBinding: ModelBinding;
  permissionProfile: PermissionProfile;
};

function bindingsEqual(a: ModelBinding, b: ModelBinding): boolean {
  const fa = [...(a.fallback ?? [])].sort();
  const fb = [...(b.fallback ?? [])].sort();
  return a.primary === b.primary && JSON.stringify(fa) === JSON.stringify(fb);
}

function permsEqual(a: PermissionProfile, b: PermissionProfile): boolean {
  return RISK_LEVELS.every((level) => a[level] === b[level]);
}

function snapshotOf(coworker: Coworker): IdentitySnapshot {
  return {
    name: coworker.name,
    avatarUrl: coworker.avatar_url ?? "",
    roleDescription: coworker.role_description,
    modelBinding: coworker.model_binding,
    permissionProfile: coworker.permission_profile,
  };
}

export default function CoworkerDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const router = useRouter();

  const [coworker, setCoworker] = useState<Coworker | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Identity form -----------------------------------------------------
  const [initial, setInitial] = useState<IdentitySnapshot | null>(null);
  const [name, setName] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");
  const [roleDescription, setRoleDescription] = useState("");
  const [primaryModel, setPrimaryModel] =
    useState<ModelId>("deepseek-v4-flash");
  const [permProfile, setPermProfile] = useState<PermissionProfile>({
    safe: "auto",
    sensitive: "approval",
    dangerous: "approval",
  });
  const [changelog, setChangelog] = useState("");
  const [isSavingIdentity, setIsSavingIdentity] = useState(false);
  const [identityError, setIdentityError] = useState<string | null>(null);
  const [identitySaved, setIdentitySaved] = useState(false);

  // Tools ---------------------------------------------------------------
  const [allTools, setAllTools] = useState<Tool[]>([]);
  const [toolsError, setToolsError] = useState<string | null>(null);
  const [attachingToolId, setAttachingToolId] = useState<string | null>(null);
  const [togglingToolId, setTogglingToolId] = useState<string | null>(null);
  const [detachingToolId, setDetachingToolId] = useState<string | null>(null);
  const [toolActionError, setToolActionError] = useState<string | null>(null);

  // Versions --------------------------------------------------------------
  const [versions, setVersions] = useState<CoworkerVersion[]>([]);
  const [versionsError, setVersionsError] = useState<string | null>(null);
  const [rollingBackVersion, setRollingBackVersion] = useState<number | null>(
    null
  );
  const [compareVersion, setCompareVersion] = useState<number | null>(null);

  // Archive ---------------------------------------------------------------
  const [archiveDialogOpen, setArchiveDialogOpen] = useState(false);
  const [isArchiving, setIsArchiving] = useState(false);
  const [archiveError, setArchiveError] = useState<string | null>(null);

  // Chat --------------------------------------------------------------
  const [isStartingChat, setIsStartingChat] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

  function applyIdentity(data: Coworker) {
    const snapshot = snapshotOf(data);
    setInitial(snapshot);
    setName(snapshot.name);
    setAvatarUrl(snapshot.avatarUrl);
    setRoleDescription(snapshot.roleDescription);
    setPrimaryModel(snapshot.modelBinding.primary);
    setPermProfile(snapshot.permissionProfile);
  }

  function loadVersions(coworkerId: string) {
    apiFetch<CoworkerVersion[]>(`/coworkers/${coworkerId}/versions`)
      .then(setVersions)
      .catch((err) => {
        setVersionsError(
          err instanceof ApiRequestError
            ? err.message
            : "Couldn't load version history."
        );
      });
  }

  useEffect(() => {
    if (!getTokens()) {
      router.push("/login");
      return;
    }
    if (!id) return;

    apiFetch<Coworker>(`/coworkers/${id}`)
      .then((data) => {
        setCoworker(data);
        applyIdentity(data);
      })
      .catch((err) => {
        setLoadError(
          err instanceof ApiRequestError
            ? err.message
            : "Couldn't load this coworker."
        );
      })
      .finally(() => setIsLoading(false));

    apiFetch<Tool[]>("/tools")
      .then(setAllTools)
      .catch((err) => {
        setToolsError(
          err instanceof ApiRequestError ? err.message : "Couldn't load tools."
        );
      });

    loadVersions(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const currentBinding: ModelBinding = { primary: primaryModel };
  const permsChanged = initial !== null && !permsEqual(permProfile, initial.permissionProfile);
  const versionAffectingChange =
    initial !== null &&
    (roleDescription !== initial.roleDescription ||
      !bindingsEqual(currentBinding, initial.modelBinding) ||
      permsChanged);
  const hasIdentityChanges =
    initial !== null &&
    (name !== initial.name || avatarUrl !== initial.avatarUrl || versionAffectingChange);

  async function handleSaveIdentity(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!coworker || !initial) return;
    setIsSavingIdentity(true);
    setIdentityError(null);
    setIdentitySaved(false);

    // Only send fields that actually changed. The contract only creates a
    // new version when role_description or model_binding *change* — always
    // sending every field on every save (even unchanged ones) risks the
    // backend treating "present in body" as "changed" and bumping the
    // version on a pure rename. See report for this judgment call.
    const body: Record<string, unknown> = {};
    if (name !== initial.name) body.name = name;
    if (avatarUrl !== initial.avatarUrl) body.avatar_url = avatarUrl || null;
    if (roleDescription !== initial.roleDescription) {
      body.role_description = roleDescription;
    }
    const bindingChanged = !bindingsEqual(currentBinding, initial.modelBinding);
    if (bindingChanged) {
      body.model_binding = currentBinding;
    }
    if (permsChanged) {
      body.permission_profile = permProfile;
    }
    if (changelog.trim()) {
      body.changelog = changelog.trim();
    }

    if (Object.keys(body).length === 0) {
      setIsSavingIdentity(false);
      return;
    }

    try {
      const updated = await apiFetch<Coworker>(`/coworkers/${coworker.id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      setCoworker(updated);
      applyIdentity(updated);
      setChangelog("");
      setIdentitySaved(true);
      if (bindingChanged || body.role_description || permsChanged) {
        loadVersions(coworker.id);
      }
    } catch (err) {
      setIdentityError(
        err instanceof ApiRequestError
          ? err.message
          : "Couldn't save changes."
      );
    } finally {
      setIsSavingIdentity(false);
    }
  }

  async function handleAttachTool(tool: Tool) {
    if (!coworker) return;
    setAttachingToolId(tool.id);
    setToolActionError(null);
    try {
      await apiFetch<CoworkerToolAttachment>(`/coworkers/${coworker.id}/tools`, {
        method: "POST",
        body: JSON.stringify({ tool_id: tool.id }),
      });
      setCoworker((prev) =>
        prev
          ? {
              ...prev,
              attached_tools: [
                ...prev.attached_tools,
                { id: tool.id, name: tool.name, enabled: true },
              ],
            }
          : prev
      );
    } catch (err) {
      setToolActionError(
        err instanceof ApiRequestError ? err.message : "Couldn't attach tool."
      );
    } finally {
      setAttachingToolId(null);
    }
  }

  async function handleToggleTool(toolId: string, enabled: boolean) {
    if (!coworker) return;
    setTogglingToolId(toolId);
    setToolActionError(null);
    try {
      await apiFetch<CoworkerToolAttachment>(`/coworkers/${coworker.id}/tools`, {
        method: "POST",
        body: JSON.stringify({ tool_id: toolId, enabled }),
      });
      setCoworker((prev) =>
        prev
          ? {
              ...prev,
              attached_tools: prev.attached_tools.map((t) =>
                t.id === toolId ? { ...t, enabled } : t
              ),
            }
          : prev
      );
    } catch (err) {
      setToolActionError(
        err instanceof ApiRequestError
          ? err.message
          : "Couldn't update the tool."
      );
    } finally {
      setTogglingToolId(null);
    }
  }

  async function handleDetachTool(toolId: string) {
    if (!coworker) return;
    setDetachingToolId(toolId);
    setToolActionError(null);
    try {
      await apiFetch(`/coworkers/${coworker.id}/tools/${toolId}`, {
        method: "DELETE",
      });
      setCoworker((prev) =>
        prev
          ? {
              ...prev,
              attached_tools: prev.attached_tools.filter(
                (t) => t.id !== toolId
              ),
            }
          : prev
      );
    } catch (err) {
      setToolActionError(
        err instanceof ApiRequestError ? err.message : "Couldn't remove tool."
      );
    } finally {
      setDetachingToolId(null);
    }
  }

  async function handleRollback(versionNumber: number) {
    if (!coworker) return;
    setRollingBackVersion(versionNumber);
    setVersionsError(null);
    try {
      const updated = await apiFetch<Coworker>(
        `/coworkers/${coworker.id}/versions/${versionNumber}/rollback`,
        { method: "POST" }
      );
      setCoworker(updated);
      applyIdentity(updated);
      setCompareVersion(null);
      loadVersions(coworker.id);
    } catch (err) {
      setVersionsError(
        err instanceof ApiRequestError
          ? err.message
          : "Couldn't roll back to that version."
      );
    } finally {
      setRollingBackVersion(null);
    }
  }

  async function handleStartChat() {
    if (!coworker) return;
    setIsStartingChat(true);
    setChatError(null);
    try {
      const workspaceId = await getWorkspaceId();
      if (!workspaceId) {
        throw new Error("Couldn't determine your current workspace.");
      }
      const conversation = await createConversation(workspaceId, coworker.id);
      router.push(`/conversations/${conversation.id}`);
    } catch (err) {
      setChatError(
        err instanceof ApiRequestError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Couldn't start a conversation."
      );
      setIsStartingChat(false);
    }
  }

  async function handleArchive() {
    if (!coworker) return;
    setIsArchiving(true);
    setArchiveError(null);
    try {
      await apiFetch(`/coworkers/${coworker.id}`, { method: "DELETE" });
      router.push("/coworkers");
    } catch (err) {
      setArchiveError(
        err instanceof ApiRequestError
          ? err.message
          : "Couldn't archive this coworker."
      );
      setIsArchiving(false);
    }
  }

  if (isLoading) {
    return (
      <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-4 py-12">
        <p className="text-sm text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (loadError || !coworker) {
    return (
      <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-4 px-4 py-12">
        <Alert variant="destructive">
          <AlertDescription>
            {loadError ?? "Couldn't load this coworker."}
          </AlertDescription>
        </Alert>
        <Link
          href="/coworkers"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          &larr; Back to coworkers
        </Link>
      </div>
    );
  }

  const attachedIds = new Set(coworker.attached_tools.map((t) => t.id));
  const availableTools = allTools.filter((t) => !attachedIds.has(t.id));
  const toolById = new Map(allTools.map((t) => [t.id, t]));

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 px-4 py-12">
      <div className="flex items-center justify-between gap-4">
        <Link
          href="/coworkers"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeftIcon className="size-3.5" />
          Coworkers
        </Link>
        <Button type="button" size="sm" disabled={isStartingChat} onClick={handleStartChat}>
          <MessageCircleIcon data-icon="inline-start" />
          {isStartingChat ? "Starting..." : "Chat"}
        </Button>
      </div>

      {chatError ? (
        <Alert variant="destructive">
          <AlertDescription>{chatError}</AlertDescription>
        </Alert>
      ) : null}

      {/* Identity ------------------------------------------------------ */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            {avatarUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={avatarUrl}
                alt=""
                className="size-12 shrink-0 rounded-full object-cover"
              />
            ) : (
              <div className="flex size-12 shrink-0 items-center justify-center rounded-full bg-muted">
                <BotIcon className="size-6 text-muted-foreground" />
              </div>
            )}
            <div>
              <CardTitle className="text-xl">{coworker.name}</CardTitle>
              <CardDescription>
                Version {coworker.current_version} &middot;{" "}
                {coworker.status === "active" ? "Active" : "Archived"}
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <form onSubmit={handleSaveIdentity}>
          <CardContent className="flex flex-col gap-4">
            {identityError ? (
              <Alert variant="destructive">
                <AlertDescription>{identityError}</AlertDescription>
              </Alert>
            ) : null}
            {identitySaved ? (
              <Alert>
                <AlertDescription>Changes saved.</AlertDescription>
              </Alert>
            ) : null}

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                type="text"
                required
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  setIdentitySaved(false);
                }}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="avatar_url">Avatar URL</Label>
              <Input
                id="avatar_url"
                type="text"
                value={avatarUrl}
                placeholder="https://..."
                onChange={(e) => {
                  setAvatarUrl(e.target.value);
                  setIdentitySaved(false);
                }}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="role_description">Role description</Label>
              <Textarea
                id="role_description"
                required
                rows={4}
                value={roleDescription}
                onChange={(e) => {
                  setRoleDescription(e.target.value);
                  setIdentitySaved(false);
                }}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="model">Model</Label>
              <Select
                value={primaryModel}
                onValueChange={(value) => {
                  setPrimaryModel(value as ModelId);
                  setIdentitySaved(false);
                }}
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
                  ?.description ??
                  "This legacy model should be changed to a current option."}
              </p>
            </div>

            {versionAffectingChange ? (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="changelog">Changelog note (optional)</Label>
                <Input
                  id="changelog"
                  type="text"
                  value={changelog}
                  onChange={(e) => setChangelog(e.target.value)}
                  placeholder="What changed and why"
                />
              </div>
            ) : null}

            <div>
              <p className="mb-1.5 text-sm font-medium">Tool permissions</p>
              <p className="mb-2.5 text-xs text-muted-foreground">
                Whether this coworker runs a tool automatically or waits for your approval,
                by risk level.
              </p>
              <div className="grid gap-2 sm:grid-cols-3">
                {RISK_LEVELS.map((level) => {
                  const locked = level === "dangerous";
                  return (
                    <div key={level} className="flex flex-col gap-1.5 rounded-lg border p-2.5">
                      <span className="text-xs font-medium capitalize text-muted-foreground">
                        {level}
                      </span>
                      <Select
                        value={permProfile[level]}
                        disabled={locked}
                        onValueChange={(value) => {
                          setPermProfile((current) => ({
                            ...current,
                            [level]: value as "auto" | "approval",
                          }));
                          setIdentitySaved(false);
                        }}
                      >
                        <SelectTrigger className="h-8 w-full" aria-label={`${level} tool policy`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {!locked ? <SelectItem value="auto">Automatic</SelectItem> : null}
                          <SelectItem value="approval">Needs approval</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  );
                })}
              </div>
              <p className="mt-1.5 text-xs text-muted-foreground">
                Dangerous tools always require approval and can&apos;t be automated.
              </p>
            </div>
          </CardContent>
          <CardFooter>
            <Button type="submit" disabled={isSavingIdentity || !hasIdentityChanges}>
              {isSavingIdentity ? "Saving..." : "Save changes"}
            </Button>
          </CardFooter>
        </form>
      </Card>

      {/* Tools ----------------------------------------------------------- */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Attached tools</CardTitle>
          <CardDescription>
            Tools this coworker can call, with their approval requirement.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {toolActionError ? (
            <Alert variant="destructive">
              <AlertDescription>{toolActionError}</AlertDescription>
            </Alert>
          ) : null}

          {coworker.attached_tools.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No tools attached yet.
            </p>
          ) : (
            <ul className="flex flex-col divide-y">
              {coworker.attached_tools.map((t) => {
                const full = toolById.get(t.id);
                return (
                  <li
                    key={t.id}
                    className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{t.name}</span>
                      {full ? (
                        <Badge className={RISK_BADGE_CLASS[full.risk_classification]}>
                          {RISK_LABELS[full.risk_classification]}
                        </Badge>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-3">
                      <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <Switch
                          size="sm"
                          checked={t.enabled}
                          disabled={togglingToolId === t.id}
                          onCheckedChange={(checked) =>
                            handleToggleTool(t.id, checked)
                          }
                        />
                        {t.enabled ? "Enabled" : "Disabled"}
                      </label>
                      <Button
                        type="button"
                        variant="destructive"
                        size="sm"
                        disabled={detachingToolId === t.id}
                        onClick={() => handleDetachTool(t.id)}
                      >
                        {detachingToolId === t.id ? "Removing..." : "Remove"}
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          <div className="flex flex-col gap-2 border-t pt-4">
            <p className="text-sm font-medium">Add a tool</p>
            {toolsError ? (
              <Alert variant="destructive">
                <AlertDescription>{toolsError}</AlertDescription>
              </Alert>
            ) : availableTools.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                {allTools.length === 0
                  ? "Loading available tools..."
                  : "All available tools are already attached."}
              </p>
            ) : (
              <ul className="flex flex-col divide-y">
                {availableTools.map((tool) => (
                  <li
                    key={tool.id}
                    className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
                  >
                    <div className="flex min-w-0 flex-col gap-0.5">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{tool.name}</span>
                        <Badge className={RISK_BADGE_CLASS[tool.risk_classification]}>
                          {RISK_LABELS[tool.risk_classification]}
                        </Badge>
                      </div>
                      <span className="truncate text-xs text-muted-foreground">
                        {tool.description}
                      </span>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={attachingToolId === tool.id}
                      onClick={() => handleAttachTool(tool)}
                    >
                      {attachingToolId === tool.id ? "Attaching..." : "Attach"}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Version history --------------------------------------------- */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Version history</CardTitle>
          <CardDescription>
            Every change to role or model creates a new version. Roll back to
            restore an older configuration as a new version.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {versionsError ? (
            <Alert variant="destructive">
              <AlertDescription>{versionsError}</AlertDescription>
            </Alert>
          ) : null}

          {versions.length === 0 ? (
            <p className="text-sm text-muted-foreground">Loading history...</p>
          ) : (
            <ul className="flex flex-col divide-y">
              {versions.map((version) => {
                const isCurrent =
                  version.version_number === coworker.current_version;
                const isComparing = compareVersion === version.version_number;
                const roleChanged =
                  version.role_description !== coworker.role_description;
                const modelChanged = !bindingsEqual(
                  version.model_binding,
                  coworker.model_binding
                );

                return (
                  <li key={version.id} className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex flex-col gap-0.5">
                        <span className="text-sm font-medium">
                          Version {version.version_number}
                          {isCurrent ? (
                            <span className="ml-2 rounded-full bg-secondary px-2 py-0.5 text-xs font-normal text-secondary-foreground">
                              Current
                            </span>
                          ) : null}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {new Date(version.created_at).toLocaleString()}
                          {version.changelog ? ` — ${version.changelog}` : ""}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() =>
                            setCompareVersion(isComparing ? null : version.version_number)
                          }
                        >
                          {isComparing ? "Hide comparison" : "Compare to current"}
                        </Button>
                        {!isCurrent ? (
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={rollingBackVersion === version.version_number}
                            onClick={() => handleRollback(version.version_number)}
                          >
                            {rollingBackVersion === version.version_number
                              ? "Rolling back..."
                              : "Roll back to this version"}
                          </Button>
                        ) : null}
                      </div>
                    </div>

                    {isComparing ? (
                      <div className="flex flex-col gap-2 rounded-lg border bg-muted/30 p-3 text-xs">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">Role description</span>
                          <Badge variant={roleChanged ? "outline" : "secondary"}>
                            {roleChanged ? "Changed" : "Same as current"}
                          </Badge>
                        </div>
                        <p className="text-muted-foreground">
                          {version.role_description}
                        </p>
                        <div className="flex items-center gap-2">
                          <span className="font-medium">Model binding</span>
                          <Badge variant={modelChanged ? "outline" : "secondary"}>
                            {modelChanged ? "Changed" : "Same as current"}
                          </Badge>
                        </div>
                        <p className="text-muted-foreground">
                          {/* Older versions may reference a retired model id;
                              fall back to the raw id rather than showing
                              "undefined". */}
                          {MODEL_LABELS[version.model_binding.primary] ??
                            version.model_binding.primary}
                          {version.model_binding.fallback?.length
                            ? ` (fallback: ${version.model_binding.fallback
                                .map((m) => MODEL_LABELS[m] ?? m)
                                .join(", ")})`
                            : ""}
                        </p>
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Archive --------------------------------------------------------- */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Archive coworker</CardTitle>
          <CardDescription>
            Removes this coworker from your roster. This can&apos;t be undone
            from this screen.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {archiveError ? (
            <Alert variant="destructive">
              <AlertDescription>{archiveError}</AlertDescription>
            </Alert>
          ) : null}
          <Dialog open={archiveDialogOpen} onOpenChange={setArchiveDialogOpen}>
            <DialogTrigger asChild>
              <Button type="button" variant="destructive" className="w-fit">
                Archive coworker
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Archive {coworker.name}?</DialogTitle>
                <DialogDescription>
                  {coworker.name} will disappear from your coworkers roster
                  and can no longer be chatted with. This can&apos;t be undone
                  from this screen.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setArchiveDialogOpen(false)}
                  disabled={isArchiving}
                >
                  Cancel
                </Button>
                <Button
                  type="button"
                  variant="destructive"
                  onClick={handleArchive}
                  disabled={isArchiving}
                >
                  {isArchiving ? "Archiving..." : "Archive coworker"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardContent>
      </Card>
    </div>
  );
}
