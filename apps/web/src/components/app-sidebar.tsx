"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  PlusIcon,
  HomeIcon,
  MessageSquareIcon,
  Users,
  ListTodo,
  MessageSquare,
  Workflow,
  FolderIcon,
  BookOpen,
  Store,
  Coins,
  BarChart3,
  ScrollText,
  Search,
  Landmark,
  Sparkles,
  Mic,
  Settings,
  Building2,
  Plug,
  ShieldAlert,
  Cpu,
  Lock,
  ChevronDown,
  Trash2Icon,
} from "lucide-react";

import { CoworkerStatusGlyph } from "@/components/coworker-status";
import { Wordmark } from "@/components/logo";
import { SidebarUser } from "@/components/sidebar-user";
import { WorkspaceSwitcher } from "@/components/workspace-switcher";
import { apiFetch } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import { deleteConversation } from "@/lib/chat";
import { useCoworkerStatuses } from "@/lib/coworker-status";
import type { Conversation, Coworker } from "@/lib/types";

// `match` lists extra path prefixes that should keep this item highlighted —
// e.g. Coworkers stays active on /agent-teams because Teams is now a sub-tab
// of the Coworkers section rather than its own top-level destination.
type NavItem = { href: string; label: string; icon: LucideIcon; match?: string[] };
type NavGroup = { label: string; items: NavItem[] };

// The everyday surface — kept short on purpose. A new user sees eight
// destinations, not twenty-two. Related screens (Teams, Approvals, Memory,
// Artifacts) live as sub-tabs of these, not as separate rail entries.
const PRIMARY: NavItem[] = [
  { href: "/home", label: "Home", icon: HomeIcon },
  { href: "/coworkers", label: "Coworkers", icon: Users, match: ["/agent-teams"] },
  { href: "/tasks", label: "Tasks", icon: ListTodo, match: ["/approvals"] },
  { href: "/conversations", label: "Conversations", icon: MessageSquare },
  { href: "/research", label: "Research", icon: Search },
  { href: "/knowledge", label: "Knowledge", icon: BookOpen, match: ["/memory", "/artifacts"] },
  { href: "/projects", label: "Projects", icon: FolderIcon },
  { href: "/workflows", label: "Workflows", icon: Workflow },
  { href: "/marketplace", label: "Marketplace", icon: Store },
];

// Advanced + admin surface, collapsed by default (progressive disclosure).
// A group auto-expands only when one of its own routes is active.
// NOTE: these are hidden, not permission-gated — true role gating needs a
// `role` field on the User/membership API, which doesn't exist yet.
const COLLAPSIBLE: NavGroup[] = [
  {
    label: "More",
    items: [
      { href: "/observability/usage", label: "Usage", icon: BarChart3 },
      { href: "/observability/audit", label: "Audit log", icon: ScrollText },
      { href: "/governance", label: "Governance", icon: Landmark },
      { href: "/evolution", label: "Adaptive collaboration", icon: Sparkles },
      { href: "/voice", label: "Live voice", icon: Mic },
      { href: "/creator", label: "Creator payouts", icon: Coins },
    ],
  },
  {
    label: "Settings",
    items: [
      { href: "/settings/workspace", label: "Workspace", icon: Settings },
      { href: "/settings/organization", label: "Organization", icon: Building2 },
      { href: "/settings/integrations", label: "Integrations", icon: Plug },
      { href: "/settings/enterprise", label: "Enterprise controls", icon: ShieldAlert },
      { href: "/settings/provider-credentials", label: "Model providers", icon: Cpu },
      { href: "/settings/mfa", label: "Security", icon: Lock },
    ],
  },
];

function isActive(pathname: string, item: NavItem) {
  const targets = [item.href, ...(item.match ?? [])];
  return targets.some((href) => pathname === href || pathname.startsWith(`${href}/`));
}

function NavRow({
  item,
  pathname,
  onNavigate,
}: {
  item: NavItem;
  pathname: string;
  onNavigate?: () => void;
}) {
  const active = isActive(pathname, item);
  const Icon = item.icon;
  return (
    <li className="min-w-0">
      <Link
        href={item.href}
        onClick={onNavigate}
        aria-current={active ? "page" : undefined}
        className={`group flex min-h-9 min-w-0 items-center gap-2.5 rounded-[9px] border px-2.5 text-[0.84375rem] font-medium transition-[background-color,border-color,color,box-shadow] ${
          active
            ? "border-sidebar-border bg-card font-semibold text-foreground shadow-[var(--shadow-sm)]"
            : "border-transparent text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
        }`}
      >
        <Icon
          className={`size-4 shrink-0 transition-colors ${
            active ? "text-foreground" : "text-muted-foreground group-hover:text-foreground"
          }`}
        />
        <span className="truncate">{item.label}</span>
      </Link>
    </li>
  );
}

function CollapsibleGroup({
  group,
  pathname,
  onNavigate,
}: {
  group: NavGroup;
  pathname: string;
  onNavigate?: () => void;
}) {
  const hasActive = group.items.some((item) => isActive(pathname, item));
  // Default to open when a route inside is active; once the user toggles, their
  // choice (the override) wins. Derived — no effect needed.
  const [override, setOverride] = useState<boolean | null>(null);
  const open = override ?? hasActive;

  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={() => setOverride(!open)}
        aria-expanded={open}
        className="group flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-[0.6875rem] font-semibold uppercase tracking-wider text-muted-foreground/60 transition-colors hover:text-muted-foreground"
      >
        <span>{group.label}</span>
        <ChevronDown
          className={`ml-auto size-3.5 transition-transform duration-200 ${open ? "" : "-rotate-90"}`}
        />
      </button>
      {open ? (
        <ul className="grid gap-0.5">
          {group.items.map((item) => (
            <NavRow key={item.href} item={item} pathname={pathname} onNavigate={onNavigate} />
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function AppSidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const [recents, setRecents] = useState<Conversation[]>([]);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [coworkers, setCoworkers] = useState<Coworker[]>([]);
  const statuses = useCoworkerStatuses(workspaceId, 30_000);

  useEffect(() => {
    if (!getTokens()) return;
    void (async () => {
      const id = await getWorkspaceId();
      if (!id) return;
      setWorkspaceId(id);
      try {
        const convs = await apiFetch<Conversation[]>(`/conversations?workspace_id=${id}`);
        setRecents(convs.slice(0, 6));
      } catch {
        // Recents are supplementary; the section just stays hidden.
      }
      try {
        const roster = await apiFetch<Coworker[]>(`/workspaces/${id}/coworkers`);
        setCoworkers(roster.slice(0, 8));
      } catch {
        // Same: the coworkers section just stays hidden.
      }
    })();
  }, [pathname]);

  async function handleDeleteRecent(conv: Conversation) {
    if (!window.confirm(`Delete "${conv.title || "Untitled conversation"}"? Its messages are removed permanently.`)) return;
    setDeletingId(conv.id);
    try {
      await deleteConversation(conv.id);
      setRecents((current) => current.filter((c) => c.id !== conv.id));
      if (pathname.startsWith(`/conversations/${conv.id}`)) {
        router.push("/conversations");
      }
    } catch {
      // Row stays; the next recents refresh reflects reality.
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <Link
        href="/home"
        onClick={onNavigate}
        aria-label="Deep-Foundry home"
        className="flex items-center gap-2.5 px-[18px] pb-3 pt-[18px]"
      >
        <Wordmark />
        <span className="sr-only">Self-hosted instance</span>
      </Link>

      <WorkspaceSwitcher />

      <div className="px-3 pb-2">
        <Link
          href="/home"
          onClick={onNavigate}
          className="flex min-h-9 items-center justify-center gap-2 rounded-[9px] bg-foreground px-3 text-[0.8125rem] font-semibold text-background shadow-[var(--shadow-sm)] transition-[background-color,box-shadow] hover:bg-foreground/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-sidebar"
        >
          <PlusIcon className="size-4 shrink-0" />
          New task
        </Link>
      </div>

      <nav
        aria-label="Primary navigation"
        className="min-w-0 flex-1 overflow-x-hidden overflow-y-auto px-3 pb-4"
      >
        <ul className="grid gap-0.5">
          {PRIMARY.map((item) => (
            <NavRow key={item.href} item={item} pathname={pathname} onNavigate={onNavigate} />
          ))}
        </ul>

        {COLLAPSIBLE.map((group) => (
          <CollapsibleGroup
            key={group.label}
            group={group}
            pathname={pathname}
            onNavigate={onNavigate}
          />
        ))}

        {coworkers.length > 0 ? (
          <div className="mt-4">
            <p className="px-3 pb-1.5 text-[0.6875rem] font-semibold uppercase tracking-wider text-muted-foreground/60">
              Your coworkers
            </p>
            <ul className="grid gap-0.5">
              {coworkers.map((coworker) => {
                const active =
                  pathname === `/coworkers/${coworker.id}` ||
                  pathname.startsWith(`/coworkers/${coworker.id}/`);
                const status = statuses.get(coworker.id);
                return (
                  <li key={coworker.id} className="min-w-0">
                    <Link
                      href={`/coworkers/${coworker.id}`}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      title={status?.detail || undefined}
                      className={`group flex min-h-8 min-w-0 items-center gap-2.5 rounded-md px-3 text-[0.8125rem] transition-colors ${
                        active
                          ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                          : "text-muted-foreground hover:bg-sidebar-accent/55 hover:text-sidebar-accent-foreground"
                      }`}
                    >
                      {coworker.avatar_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={coworker.avatar_url}
                          alt=""
                          className="size-4 shrink-0 rounded-full object-cover"
                        />
                      ) : (
                        <span className="flex size-4 shrink-0 items-center justify-center rounded-full bg-secondary text-[9px] font-semibold uppercase text-muted-foreground">
                          {coworker.name.slice(0, 1)}
                        </span>
                      )}
                      <span className="min-w-0 flex-1 truncate">{coworker.name}</span>
                      {status ? (
                        <span className="ml-auto flex shrink-0 items-center">
                          <CoworkerStatusGlyph state={status.state} className="size-3.5" />
                        </span>
                      ) : null}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}

        {recents.length > 0 ? (
          <div className="mt-4">
            <p className="px-3 pb-1.5 text-[0.6875rem] font-semibold uppercase tracking-wider text-muted-foreground/60">
              Recents
            </p>
            <ul className="grid gap-0.5">
              {recents.map((conv) => {
                const active =
                  pathname === `/conversations/${conv.id}` ||
                  pathname.startsWith(`/conversations/${conv.id}/`);
                return (
                  <li key={conv.id} className="group/recent relative min-w-0">
                    <Link
                      href={`/conversations/${conv.id}`}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      title={conv.title || "Untitled conversation"}
                      className={`group flex min-h-8 min-w-0 items-start gap-2.5 rounded-md px-3 py-2 pr-8 text-[0.8125rem] transition-colors ${
                        active
                          ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                          : "text-muted-foreground hover:bg-sidebar-accent/55 hover:text-sidebar-accent-foreground"
                      }`}
                    >
                      <MessageSquareIcon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground/60 group-hover:text-foreground/70" />
                      <span className="line-clamp-2 min-w-0 flex-1 whitespace-normal leading-4 [overflow-wrap:anywhere]">
                        {conv.title || "Untitled conversation"}
                      </span>
                    </Link>
                    <button
                      type="button"
                      onClick={() => void handleDeleteRecent(conv)}
                      disabled={deletingId === conv.id}
                      aria-label={`Delete conversation ${conv.title || "Untitled conversation"}`}
                      className="absolute right-1.5 top-1/2 flex size-5 -translate-y-1/2 items-center justify-center rounded text-muted-foreground/60 opacity-0 transition-opacity hover:text-destructive focus-visible:opacity-100 group-hover/recent:opacity-100 disabled:opacity-40"
                    >
                      <Trash2Icon className="size-3.5" />
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}
      </nav>

      <SidebarUser />
    </div>
  );
}
