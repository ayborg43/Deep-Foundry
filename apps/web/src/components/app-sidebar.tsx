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
  ShieldCheck,
  MessageSquare,
  Network,
  Workflow,
  BookOpen,
  Brain,
  FileText,
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
} from "lucide-react";

import { apiFetch } from "@/lib/api";
import { getTokens, getWorkspaceId } from "@/lib/auth";
import type { Conversation } from "@/lib/types";

type NavItem = { href: string; label: string; icon: LucideIcon };
type NavGroup = { label: string; items: NavItem[] };

const GROUPS: NavGroup[] = [
  {
    label: "Workspace",
    items: [
      { href: "/coworkers", label: "Coworkers", icon: Users },
      { href: "/tasks", label: "Tasks", icon: ListTodo },
      { href: "/approvals", label: "Approvals", icon: ShieldCheck },
      { href: "/conversations", label: "Conversations", icon: MessageSquare },
    ],
  },
  {
    label: "Build",
    items: [
      { href: "/agent-teams", label: "Agent teams", icon: Network },
      { href: "/workflows", label: "Workflows", icon: Workflow },
      { href: "/knowledge", label: "Knowledge", icon: BookOpen },
      { href: "/memory", label: "Memory", icon: Brain },
      { href: "/artifacts", label: "Artifacts", icon: FileText },
    ],
  },
  {
    label: "Discover",
    items: [
      { href: "/marketplace", label: "Marketplace", icon: Store },
      { href: "/creator", label: "Creator payouts", icon: Coins },
    ],
  },
  {
    label: "Operate",
    items: [
      { href: "/observability/usage", label: "Usage", icon: BarChart3 },
      { href: "/observability/audit", label: "Audit log", icon: ScrollText },
      { href: "/governance", label: "Governance", icon: Landmark },
      { href: "/evolution", label: "Adaptive collaboration", icon: Sparkles },
      { href: "/voice", label: "Live voice", icon: Mic },
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

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
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

      <nav
        aria-label="Primary navigation"
        className="flex-1 overflow-y-auto px-3 pb-4"
      >
        {GROUPS.map((group) => (
          <div key={group.label} className="mb-4">
            <p className="px-3 pb-1.5 text-[0.6875rem] font-medium uppercase tracking-wider text-muted-foreground/70">
              {group.label}
            </p>
            <ul className="grid gap-0.5">
              {group.items.map((item) => {
                const active = isActive(pathname, item.href);
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      className={`flex min-h-9 items-center gap-2.5 rounded-md px-3 text-sm transition-colors ${
                        active
                          ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                          : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
                      }`}
                    >
                      <Icon className={`size-4 shrink-0 ${active ? "text-primary" : ""}`} />
                      <span className="truncate">{item.label}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}

        {recents.length > 0 ? (
          <div className="mb-4">
            <p className="px-3 pb-1.5 text-[0.6875rem] font-medium uppercase tracking-wider text-muted-foreground/70">
              Recents
            </p>
            <ul className="grid gap-0.5">
              {recents.map((conv) => {
                const active = isActive(pathname, `/conversations/${conv.id}`);
                return (
                  <li key={conv.id}>
                    <Link
                      href={`/conversations/${conv.id}`}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      className={`flex min-h-9 items-center gap-2.5 rounded-md px-3 text-sm transition-colors ${
                        active
                          ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                          : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
                      }`}
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
