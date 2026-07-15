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

function navItemClass(active: boolean) {
  return `flex min-h-9 items-center gap-2.5 rounded-md px-3 text-sm transition-colors ${
    active
      ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
      : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
  }`;
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
        className={navItemClass(active)}
      >
        <Icon className={`size-4 shrink-0 ${active ? "text-primary" : ""}`} />
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
    <div className="mb-1">
      <button
        type="button"
        onClick={() => setOverride(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-[0.6875rem] font-medium uppercase tracking-wider text-muted-foreground/70 transition-colors hover:text-muted-foreground"
      >
        <span>{group.label}</span>
        <ChevronDown
          className={`ml-auto size-3.5 transition-transform ${open ? "" : "-rotate-90"}`}
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
        className="flex items-center gap-2.5 px-5 pt-5 pb-4"
      >
        <span aria-hidden className="text-xl leading-none text-primary">✳</span>
        <span className="font-heading text-lg font-semibold tracking-tight">Deep-Foundry</span>
      </Link>

      <div className="grid gap-0.5 px-3 pb-3">
        <Link
          href="/home"
          onClick={onNavigate}
          className="flex min-h-9 items-center gap-2.5 rounded-md bg-primary/12 px-3 text-sm font-medium text-primary transition-colors hover:bg-primary/18"
        >
          <PlusIcon className="size-4 shrink-0" />
          New
        </Link>
        <Link
          href="/home"
          onClick={onNavigate}
          aria-current={pathname === "/home" ? "page" : undefined}
          className={`flex min-h-9 items-center gap-2.5 rounded-md px-3 text-sm transition-colors ${
            pathname === "/home"
              ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
              : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
          }`}
        >
          <HomeIcon className={`size-4 shrink-0 ${pathname === "/home" ? "text-primary" : ""}`} />
          Home
        </Link>
      </div>

      <nav aria-label="Primary navigation" className="flex-1 overflow-y-auto px-3 pb-4">
        <ul className="mb-4 grid gap-0.5">
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
          <div className="mb-4 mt-4">
            <p className="px-3 pb-1.5 text-[0.6875rem] font-medium uppercase tracking-wider text-muted-foreground/70">
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
                      className={navItemClass(active)}
                    >
                      <MessageSquareIcon className="size-4 shrink-0 opacity-70" />
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
