"use client";

import { type FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PlusIcon, ShieldCheckIcon, Trash2Icon, UsersIcon } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { PageHeader } from "@/components/page-header";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import type { User, Workspace } from "@/lib/types";

type Member = { id: string; user_id: string; email: string; role: string };
type Floor = { id: string; risk: string; min_required_policy: string; enforced: boolean };

// Assignable roles — kept to the set the API accepts on both invite (POST)
// and role change (PATCH), so a role you can assign is always one you can
// later change to (no dead ends).
const ROLES = [
  { value: "admin", label: "Admin", hint: "Manage members, settings, and everything below." },
  { value: "member", label: "Member", hint: "Use the workspace and its coworkers." },
  { value: "guest", label: "Guest", hint: "Limited, invite-only access." },
] as const;

function roleLabel(role: string) {
  return ROLES.find((r) => r.value === role)?.label ?? role.replace(/_/g, " ");
}

export default function OrganizationSettingsPage() {
  const router = useRouter();
  const [workspaceId, setWorkspaceId] = useState("");
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [me, setMe] = useState<User | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [floors, setFloors] = useState<Floor[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [bundle, setBundle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);

  const myMembership = members.find((m) => m.user_id === me?.id);
  const canManage = myMembership?.role === "owner" || myMembership?.role === "admin";

  async function load(id: string) {
    const [m, f] = await Promise.all([
      apiFetch<Member[]>(`/workspaces/${id}/members`),
      apiFetch<Floor[]>(`/workspaces/${id}/policy-floors`),
    ]);
    setMembers(m);
    setFloors(f);
  }

  useEffect(() => {
    if (!getTokens()) {
      router.push("/login");
      return;
    }
    void (async () => {
      try {
        setMe(await apiFetch<User>("/me"));
      } catch {
        /* non-fatal: only used to mark "You" and derive permissions */
      }
      const id = await getWorkspaceId();
      if (!id) return;
      setWorkspaceId(id);
      try {
        setWorkspace(await apiFetch<Workspace>(`/workspaces/${id}`));
        await load(id);
      } catch {
        setError("Couldn't load organization settings.");
      }
    })();
  }, [router]);

  async function invite(event: FormEvent) {
    event.preventDefault();
    if (!email.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await apiFetch(`/workspaces/${workspaceId}/members`, {
        method: "POST",
        body: JSON.stringify({ email: email.trim(), role }),
      });
      setNotice(
        `${email.trim()} was added as ${roleLabel(role)}. They sign in with this email (via password reset or Google).`,
      );
      setEmail("");
      await load(workspaceId);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn't add that member.");
    } finally {
      setBusy(false);
    }
  }

  async function changeRole(member: Member, nextRole: string) {
    if (nextRole === member.role) return;
    setPendingId(member.id);
    setError(null);
    try {
      await apiFetch(`/workspaces/${workspaceId}/members/${member.id}`, {
        method: "PATCH",
        body: JSON.stringify({ role: nextRole }),
      });
      await load(workspaceId);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn't change that role.");
    } finally {
      setPendingId(null);
    }
  }

  async function remove(member: Member) {
    setPendingId(member.id);
    setError(null);
    try {
      await apiFetch(`/workspaces/${workspaceId}/members/${member.id}`, { method: "DELETE" });
      setConfirmingId(null);
      await load(workspaceId);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn't remove that member.");
    } finally {
      setPendingId(null);
    }
  }

  async function enforce(risk: "safe" | "sensitive" | "dangerous") {
    setBusy(true);
    try {
      await apiFetch(`/workspaces/${workspaceId}/policy-floors`, {
        method: "POST",
        body: JSON.stringify({ tool_risk_classification: risk, enforced: true }),
      });
      await load(workspaceId);
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Couldn't update the policy floor.");
    } finally {
      setBusy(false);
    }
  }

  async function importBundle() {
    setBusy(true);
    setError(null);
    try {
      await apiFetch(`/workspaces/${workspaceId}/coworkers/import`, {
        method: "POST",
        body: JSON.stringify({ bundle: JSON.parse(bundle) }),
      });
      setBundle("");
      setNotice("Coworker imported into this workspace.");
    } catch (err) {
      setError(
        err instanceof ApiRequestError
          ? err.message
          : err instanceof SyntaxError
            ? "The coworker bundle is not valid JSON."
            : "Couldn't import that coworker.",
      );
    } finally {
      setBusy(false);
    }
  }

  const isPersonal = workspace?.type !== "organization";

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-4 py-10 sm:px-6">
      <PageHeader
        title={workspace?.name ?? "Organization"}
        description="Manage who's in this workspace and what they can do."
      />

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {notice ? (
        <Alert>
          <AlertDescription>{notice}</AlertDescription>
        </Alert>
      ) : null}

      {isPersonal ? (
        <Alert>
          <AlertDescription>
            This is your personal workspace, so it&apos;s just you. Create an organization from the
            workspace switcher to invite teammates.
          </AlertDescription>
        </Alert>
      ) : null}

      {/* Invite */}
      {canManage ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Invite a member</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={invite} className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <div className="grid flex-1 gap-1.5">
                <Label htmlFor="member-email">Email</Label>
                <Input
                  id="member-email"
                  type="email"
                  required
                  placeholder="teammate@company.com"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="member-role">Role</Label>
                <Select value={role} onValueChange={setRole}>
                  <SelectTrigger id="member-role" className="w-full sm:w-44">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ROLES.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button disabled={busy || !email.trim()}>
                <PlusIcon data-icon="inline-start" />
                Invite
              </Button>
            </form>
            <p className="mt-2 text-xs text-muted-foreground">
              {ROLES.find((r) => r.value === role)?.hint}
            </p>
          </CardContent>
        </Card>
      ) : null}

      {/* Members */}
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <UsersIcon className="size-4" />
            Members
          </CardTitle>
          <Badge variant="outline">{members.length}</Badge>
        </CardHeader>
        <CardContent className="flex flex-col gap-1.5">
          {members.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">No members yet.</p>
          ) : (
            members.map((member) => {
              const isOwner = member.role === "owner";
              const isSelf = member.user_id === me?.id;
              const rowBusy = pendingId === member.id;
              return (
                <div
                  key={member.id}
                  className="flex items-center gap-3 rounded-lg border border-border px-3 py-2.5"
                >
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                    {member.email.charAt(0).toUpperCase()}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {member.email}
                      {isSelf ? <span className="ml-1.5 text-xs text-muted-foreground">You</span> : null}
                    </p>
                  </div>

                  {canManage && !isOwner ? (
                    <Select
                      value={member.role}
                      onValueChange={(next) => void changeRole(member, next)}
                      disabled={rowBusy}
                    >
                      <SelectTrigger className="h-8 w-32" aria-label={`Role for ${member.email}`}>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {ROLES.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Badge variant={isOwner ? "default" : "outline"}>{roleLabel(member.role)}</Badge>
                  )}

                  {canManage && !isOwner && !isSelf ? (
                    confirmingId === member.id ? (
                      <div className="flex items-center gap-1">
                        <Button
                          size="sm"
                          variant="destructive"
                          disabled={rowBusy}
                          onClick={() => void remove(member)}
                        >
                          {rowBusy ? "Removing…" : "Remove"}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setConfirmingId(null)}>
                          Cancel
                        </Button>
                      </div>
                    ) : (
                      <Button
                        size="icon-sm"
                        variant="ghost"
                        aria-label={`Remove ${member.email}`}
                        onClick={() => setConfirmingId(member.id)}
                      >
                        <Trash2Icon />
                      </Button>
                    )
                  ) : null}
                </div>
              );
            })
          )}
        </CardContent>
      </Card>

      {/* Policy floors */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldCheckIcon className="size-4" />
            Policy floors
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          {(["safe", "sensitive", "dangerous"] as const).map((risk) => {
            const active = floors.some((f) => f.risk === risk && f.enforced);
            return (
              <div key={risk} className="flex flex-col gap-3 rounded-lg border border-border p-3">
                <div>
                  <p className="font-medium capitalize">{risk} tools</p>
                  <p className="text-xs text-muted-foreground">
                    Minimum: {active ? "approval required" : "coworker policy"}
                  </p>
                </div>
                <Button
                  variant={active ? "secondary" : "outline"}
                  size="sm"
                  disabled={active || busy || !canManage}
                  onClick={() => void enforce(risk)}
                >
                  {active ? "Enforced" : "Require approval"}
                </Button>
              </div>
            );
          })}
        </CardContent>
      </Card>

      {/* Import portable coworker */}
      {canManage ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Import a portable coworker</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="coworker-bundle">Coworker bundle (JSON)</Label>
              <Textarea
                id="coworker-bundle"
                rows={5}
                value={bundle}
                onChange={(event) => setBundle(event.target.value)}
                placeholder='{"name": "...", "role_description": "...", ...}'
              />
              <p className="text-xs text-muted-foreground">
                Bundles carry configuration, skills, and tool names. Private memory and credentials
                are never included.
              </p>
            </div>
            <Button className="w-fit" disabled={busy || !bundle.trim()} onClick={() => void importBundle()}>
              Import coworker
            </Button>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
