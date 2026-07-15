"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
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
  BookOpen,
  Store,
  Coins,
  BarChart3,
  ScrollText,
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
} from "lucide-react";

import { Wordmark } from "@/components/logo";
import { WorkspaceSwitcher } from "@/components/workspace-switcher";
import { apiFetch } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import type { Conversation } from "@/lib/types";

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
  { href: "/knowledge", label: "Knowledge", icon: BookOpen, match: ["/memory", "/artifacts"] },
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
    <li>
      <Link
        href={item.href}
        onClick={onNavigate}
        aria-current={active ? "page" : undefined}
        className={`group relative flex min-h-[2.125rem] items-center gap-2.5 rounded-md px-3 text-[0.8125rem] font-medium transition-colors ${
          active
            ? "bg-sidebar-accent text-sidebar-accent-foreground"
            : "text-muted-foreground hover:bg-sidebar-accent/55 hover:text-sidebar-accent-foreground"
        }`}
      >
        {active ? (
          <span
            aria-hidden
            className="absolute left-0 top-1/2 h-[18px] w-[3px] -translate-y-1/2 rounded-r-full bg-primary"
          />
        ) : null}
        <Icon
          className={`size-4 shrink-0 transition-colors ${
            active ? "text-primary" : "text-muted-foreground/70 group-hover:text-foreground/80"
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
  const [recents, setRecents] = useState<Conversation[]>([]);

  useEffect(() => {
    if (!getTokens()) return;
    void (async () => {
      const id = await getWorkspaceId();
      if (!id) return;
      try {
        const convs = await apiFetch<Conversation[]>(`/conversations?workspace_id=${id}`);
        setRecents(convs.slice(0, 6));
      } catch {
        // Recents are supplementary; the section just stays hidden.
      }
    })();
  }, [pathname]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Link
        href="/home"
        onClick={onNavigate}
        aria-label="Deep-Foundry home"
        className="flex items-center px-4 pt-4 pb-3.5"
      >
        <Wordmark />
      </Link>

      <WorkspaceSwitcher />

      <div className="px-3 pb-2">
        <Link
          href="/home"
          onClick={onNavigate}
          className="flex min-h-9 items-center justify-center gap-2 rounded-lg bg-primary px-3 text-[0.8125rem] font-semibold text-primary-foreground shadow-[var(--shadow-sm)] transition-[background-color,box-shadow] hover:bg-[color-mix(in_oklch,var(--primary),black_10%)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-sidebar"
        >
          <PlusIcon className="size-4 shrink-0" />
          New task
        </Link>
      </div>

      <nav aria-label="Primary navigation" className="flex-1 overflow-y-auto px-3 pb-4">
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
                  <li key={conv.id}>
                    <Link
                      href={`/conversations/${conv.id}`}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      className={`group flex min-h-8 items-center gap-2.5 rounded-md px-3 text-[0.8125rem] transition-colors ${
                        active
                          ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                          : "text-muted-foreground hover:bg-sidebar-accent/55 hover:text-sidebar-accent-foreground"
                      }`}
                    >
                      <MessageSquareIcon className="size-3.5 shrink-0 text-muted-foreground/60 group-hover:text-foreground/70" />
                      <span className="truncate">{conv.title || "Untitled conversation"}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}
      </nav>
    </div>
  );
}
