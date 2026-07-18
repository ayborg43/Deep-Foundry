"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Building2Icon,
  CheckCircle2Icon,
  EyeIcon,
  MoreHorizontalIcon,
  PlusIcon,
  ShieldCheckIcon,
  TriangleAlertIcon,
  UploadIcon,
  UserPlusIcon,
  UsersIcon,
  WrenchIcon,
} from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NewOrganizationDialog } from "@/components/new-organization-dialog";
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
import type { Coworker, User, Workspace } from "@/lib/types";

type Member = { id: string; user_id: string; email: string; role: string };
type Floor = { id: string; risk: string; min_required_policy: string; enforced: boolean };
type Tab = "coworkers" | "members" | "settings";

const ROLES = [
  { value: "admin", label: "Admin", hint: "Manage members, settings, and everything below." },
  { value: "member", label: "Member", hint: "Use the organization and chat with its coworkers." },
  { value: "guest", label: "Guest", hint: "Limited, invite-only access." },
] as const;

const ACCENTS = ["#0E8A88", "#C24C68", "#2F6FB0", "#3F7D3C", "#8A4F7D", "#B07A1E"];

function roleLabel(role: string) {
  return ROLES.find((item) => item.value === role)?.label ?? role.replace(/_/g, " ");
}

function initials(value: string) {
  return value
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

function slug(value: string) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export default function OrganizationSettingsPage() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("coworkers");
  const [workspaceId, setWorkspaceId] = useState("");
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [me, setMe] = useState<User | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [coworkers, setCoworkers] = useState<Coworker[]>([]);
  const [floors, setFloors] = useState<Floor[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [bundle, setBundle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const myMembership = members.find((member) => member.user_id === me?.id);
  const canManage = myMembership?.role === "owner" || myMembership?.role === "admin";
  const isPersonal = workspace?.type !== "organization";
  const domain = `${slug(workspace?.name || "workspace")}.foundry.dev`;
  const orgInitials = initials(workspace?.name || "Organization");

  const floorByRisk = useMemo(
    () => new Map(floors.map((floor) => [floor.risk, floor])),
    [floors],
  );

  async function load(id: string) {
    const [memberRows, floorRows, coworkerRows] = await Promise.all([
      apiFetch<Member[]>(`/workspaces/${id}/members`),
      apiFetch<Floor[]>(`/workspaces/${id}/policy-floors`),
      apiFetch<Coworker[]>(`/workspaces/${id}/coworkers`),
    ]);
    setMembers(memberRows);
    setFloors(floorRows);
    setCoworkers(coworkerRows);
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
        // The account is supplementary to the organization view.
      }
      const id = await getWorkspaceId();
      if (!id) return;
      setWorkspaceId(id);
      try {
        const row = await apiFetch<Workspace>(`/workspaces/${id}`);
        setWorkspace(row);
        await load(id);
      } catch {
        setError("Couldn't load this organization.");
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
      setNotice(`${email.trim()} was added as ${roleLabel(role)}.`);
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

  async function enforce(risk: "safe" | "sensitive" | "dangerous") {
    setBusy(true);
    setError(null);
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
      setNotice("Coworker imported into this organization.");
      await load(workspaceId);
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

  const tabs: { value: Tab; label: string; count?: number }[] = [
    { value: "coworkers", label: "Coworkers", count: coworkers.length },
    { value: "members", label: "Members", count: members.length },
    { value: "settings", label: "Settings" },
  ];

  return (
    <div className="flex min-h-full flex-col">
      <header className="flex flex-col gap-4 px-5 pt-5 sm:px-7 lg:flex-row lg:items-center">
        <span className="flex size-[52px] shrink-0 items-center justify-center rounded-[14px] bg-primary/10 text-sm font-bold text-primary ring-2 ring-primary/40 ring-offset-4 ring-offset-background">
          {orgInitials}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-[1.3125rem] font-bold tracking-[-0.02em]">
              {workspace?.name ?? "Organization"}
            </h1>
            <Badge variant="outline" className="rounded-md bg-muted px-2 text-[0.6875rem] capitalize">
              {workspace?.plan_tier || "Free"}
            </Badge>
          </div>
          <p className="mt-0.5 truncate font-mono text-[0.8125rem] text-muted-foreground">
            {domain}
          </p>
        </div>
        <Button
          variant="outline"
          className="w-fit bg-card"
          onClick={() => setCreateOpen(true)}
        >
          <PlusIcon data-icon="inline-start" />
          New organization
        </Button>
      </header>

      <div className="mt-4 flex gap-0.5 border-b border-border px-5 sm:px-7" role="tablist">
        {tabs.map((item) => {
          const active = item.value === tab;
          return (
            <button
              key={item.value}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setTab(item.value)}
              className={`min-h-11 border-b-2 px-3 text-[0.84375rem] font-semibold transition-colors ${
                active
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {item.label}
              {item.count !== undefined ? (
                <span className="ml-1.5 text-[0.6875rem] text-muted-foreground">
                  {item.count}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      <div className="fd-scroll flex-1 overflow-y-auto px-5 py-5 sm:px-7">
        {error ? (
          <Alert variant="destructive" className="mb-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}
        {notice ? (
          <Alert className="mb-4">
            <AlertDescription>{notice}</AlertDescription>
          </Alert>
        ) : null}
        {isPersonal ? (
          <Alert className="mb-4">
            <AlertDescription>
              This is your personal workspace. Create an organization to share coworkers with a team.
            </AlertDescription>
          </Alert>
        ) : null}

        {tab === "coworkers" ? (
          <section aria-labelledby="coworkers-heading">
            <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p id="coworkers-heading" className="max-w-2xl text-[0.84375rem] leading-5 text-muted-foreground">
                Coworkers assigned to <strong className="text-foreground">{workspace?.name}</strong>{" "}
                share this organization&apos;s connected tools, knowledge, and approval policy.
              </p>
              <Button asChild className="w-fit bg-foreground text-background hover:bg-foreground/90">
                <Link href="/coworkers/new">
                  <PlusIcon data-icon="inline-start" />
                  Add coworker
                </Link>
              </Button>
            </div>

            <div className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-3">
              {coworkers.map((coworker, index) => {
                const accent = ACCENTS[index % ACCENTS.length];
                const active = coworker.status === "active";
                return (
                  <article
                    key={coworker.id}
                    className="overflow-hidden rounded-[14px] border border-border bg-card transition-[border-color,box-shadow] hover:border-input hover:shadow-[var(--shadow-sm)]"
                  >
                    <div className="h-[3px]" style={{ backgroundColor: accent }} />
                    <div className="p-4">
                      <div className="flex items-start gap-3">
                        <span
                          className="flex size-11 shrink-0 items-center justify-center rounded-xl text-xs font-bold text-white"
                          style={{
                            backgroundColor: accent,
                            boxShadow: `0 0 0 2px ${accent}88, 0 0 0 4px var(--card)`,
                          }}
                        >
                          {initials(coworker.name)}
                        </span>
                        <div className="min-w-0 flex-1">
                          <Link
                            href={`/coworkers/${coworker.id}`}
                            className="font-bold text-foreground hover:text-primary"
                          >
                            {coworker.name}
                          </Link>
                          <p className="truncate text-[0.78125rem] text-muted-foreground">
                            {coworker.role_description || "AI coworker"}
                          </p>
                          <span
                            className={`mt-1.5 inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[0.6875rem] font-bold ${
                              active
                                ? "border-[#4e9a6a]/30 bg-[#4e9a6a]/10 text-[#3f7d3c] dark:text-[#72b984]"
                                : "border-border bg-muted text-muted-foreground"
                            }`}
                          >
                            <span className={`size-1.5 rounded-full ${active ? "bg-current" : "bg-muted-foreground"}`} />
                            {active ? "Ready" : "Archived"}
                          </span>
                        </div>
                        <Button asChild variant="ghost" size="icon-sm" aria-label={`Open ${coworker.name}`}>
                          <Link href={`/coworkers/${coworker.id}`}>
                            <MoreHorizontalIcon />
                          </Link>
                        </Button>
                      </div>
                      <div className="mt-3 flex items-center gap-3 border-t border-border pt-2.5 text-xs text-muted-foreground">
                        <span className="truncate font-mono text-[0.6875rem] text-foreground/75">
                          {coworker.model_binding.primary}
                        </span>
                        <span className="inline-flex items-center gap-1">
                          <WrenchIcon className="size-3" />
                          {coworker.attached_tools.length}
                        </span>
                        <span className="ml-auto inline-flex items-center gap-1">
                          <UsersIcon className="size-3" />
                          Org access
                        </span>
                      </div>
                    </div>
                  </article>
                );
              })}

              <Link
                href="/coworkers/new"
                className="flex min-h-[154px] flex-col items-center justify-center gap-2 rounded-[14px] border border-dashed border-input text-muted-foreground transition-colors hover:border-primary hover:text-primary"
              >
                <span className="flex size-10 items-center justify-center rounded-xl border border-current">
                  <PlusIcon className="size-4" />
                </span>
                <span className="text-[0.8125rem] font-semibold">Add a coworker</span>
              </Link>
            </div>
          </section>
        ) : null}

        {tab === "members" ? (
          <section aria-labelledby="members-heading">
            <div className="mb-4 flex items-center justify-between gap-4">
              <p id="members-heading" className="text-[0.84375rem] text-muted-foreground">
                People who can access <strong className="text-foreground">{workspace?.name}</strong> and its coworkers.
              </p>
            </div>

            {canManage ? (
              <form
                onSubmit={invite}
                className="mb-4 grid gap-3 rounded-xl border border-border bg-card p-4 sm:grid-cols-[1fr_10rem_auto] sm:items-end"
              >
                <div className="grid gap-1.5">
                  <Label htmlFor="member-email">Invite by email</Label>
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
                    <SelectTrigger id="member-role" className="w-full">
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
                <Button
                  disabled={busy || !email.trim()}
                  className="bg-foreground text-background hover:bg-foreground/90"
                >
                  <UserPlusIcon data-icon="inline-start" />
                  Invite
                </Button>
                <p className="text-xs text-muted-foreground sm:col-span-3">
                  {ROLES.find((item) => item.value === role)?.hint}
                </p>
              </form>
            ) : null}

            <div className="overflow-hidden rounded-xl border border-border bg-card">
              {members.length === 0 ? (
                <p className="py-10 text-center text-sm text-muted-foreground">No members yet.</p>
              ) : (
                members.map((member, index) => {
                  const isOwner = member.role === "owner";
                  const isSelf = member.user_id === me?.id;
                  return (
                    <div
                      key={member.id}
                      className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3 last:border-b-0"
                    >
                      <span
                        className="flex size-9 shrink-0 items-center justify-center rounded-[9px] text-xs font-bold text-white"
                        style={{ backgroundColor: ACCENTS[index % ACCENTS.length] }}
                      >
                        {initials(member.email)}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold">
                          {member.email}
                          {isSelf ? <span className="ml-1.5 text-xs font-normal text-muted-foreground">You</span> : null}
                        </p>
                        <p className="text-xs text-muted-foreground">Organization member</p>
                      </div>
                      {canManage && !isOwner ? (
                        <Select
                          value={member.role}
                          onValueChange={(next) => void changeRole(member, next)}
                          disabled={pendingId === member.id}
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
                    </div>
                  );
                })
              )}
            </div>
          </section>
        ) : null}

        {tab === "settings" ? (
          <section className="max-w-2xl space-y-3.5" aria-labelledby="settings-heading">
            <h2 id="settings-heading" className="sr-only">Organization settings</h2>
            <div className="rounded-[13px] border border-border bg-card p-5">
              <p className="mb-3 text-[0.6875rem] font-bold uppercase tracking-[0.05em] text-muted-foreground">
                General
              </p>
              <div className="grid gap-4">
                <div className="grid gap-1.5">
                  <Label htmlFor="org-name">Organization name</Label>
                  <Input id="org-name" value={workspace?.name || ""} readOnly />
                </div>
                <div className="grid gap-1.5">
                  <Label htmlFor="org-domain">Instance domain</Label>
                  <div className="flex overflow-hidden rounded-[9px] border border-input bg-card focus-within:ring-3 focus-within:ring-ring/20">
                    <Input
                      id="org-domain"
                      value={slug(workspace?.name || "")}
                      readOnly
                      className="rounded-none border-0 font-mono shadow-none focus-visible:ring-0"
                    />
                    <span className="flex items-center border-l border-border bg-muted px-3 font-mono text-xs text-muted-foreground">
                      .foundry.dev
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div className="rounded-[13px] border border-border bg-card p-5">
              <p className="mb-1 text-[0.6875rem] font-bold uppercase tracking-[0.05em] text-muted-foreground">
                Default approval policy
              </p>
              <p className="mb-4 text-[0.8125rem] leading-5 text-muted-foreground">
                Applied to every new coworker in this organization. Dangerous tools always require approval.
              </p>
              <div className="grid gap-2">
                {([
                  { risk: "safe", label: "Safe tools", icon: ShieldCheckIcon, color: "#4E9A6A", defaultLabel: "Auto-run" },
                  { risk: "sensitive", label: "Sensitive tools", icon: EyeIcon, color: "#C79A2E", defaultLabel: "Coworker policy" },
                  { risk: "dangerous", label: "Dangerous tools", icon: TriangleAlertIcon, color: "#D65A4A", defaultLabel: "Ask every time · locked" },
                ] as const).map((item) => {
                  const active = floorByRisk.get(item.risk)?.enforced;
                  const Icon = item.icon;
                  return (
                    <div key={item.risk} className="flex min-h-10 items-center gap-2.5 text-[0.8125rem]">
                      <Icon className="size-4" style={{ color: item.color }} />
                      <span className="flex-1 font-medium">{item.label}</span>
                      <span className="text-muted-foreground">
                        {active ? "Approval required" : item.defaultLabel}
                      </span>
                      {!active && item.risk !== "dangerous" && canManage ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={busy}
                          onClick={() => void enforce(item.risk)}
                        >
                          Enforce
                        </Button>
                      ) : active ? (
                        <CheckCircle2Icon className="size-4 text-[#4E9A6A]" aria-label="Enforced" />
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>

            {canManage ? (
              <div className="rounded-[13px] border border-border bg-card p-5">
                <p className="mb-3 text-[0.6875rem] font-bold uppercase tracking-[0.05em] text-muted-foreground">
                  Import portable coworker
                </p>
                <Label htmlFor="coworker-bundle">Coworker bundle (JSON)</Label>
                <Textarea
                  id="coworker-bundle"
                  className="mt-1.5 font-mono text-xs"
                  rows={5}
                  value={bundle}
                  onChange={(event) => setBundle(event.target.value)}
                  placeholder='{"name": "...", "role_description": "..."}'
                />
                <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <p className="text-xs leading-5 text-muted-foreground">
                    Private memory and credentials are never included.
                  </p>
                  <Button
                    disabled={busy || !bundle.trim()}
                    onClick={() => void importBundle()}
                    className="w-fit bg-foreground text-background hover:bg-foreground/90"
                  >
                    <UploadIcon data-icon="inline-start" />
                    Import coworker
                  </Button>
                </div>
              </div>
            ) : null}

            <div className="flex items-center gap-4 rounded-[13px] border border-destructive/30 bg-destructive/5 p-4">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-destructive/10 text-destructive">
                <Building2Icon className="size-4" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold">Organization ownership</p>
                <p className="text-xs leading-5 text-muted-foreground">
                  Transfer ownership before deleting or leaving this organization.
                </p>
              </div>
            </div>
          </section>
        ) : null}
      </div>

      <NewOrganizationDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
