"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { MenuIcon, XIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { AppSidebar } from "@/components/app-sidebar";
import { SectionTabs } from "@/components/section-tabs";
import { NotificationBell } from "@/components/notification-bell";
import { Wordmark } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { apiFetch } from "@/lib/api";
import { getTokens } from "@/lib/auth";
import type { User } from "@/lib/types";

// The marketing home gets the slim topbar (logo + Log in / Get started nav).
function isMarketingRoute(pathname: string): boolean {
  return pathname === "/";
}

// Auth pages own their entire viewport — no shared nav. They already carry
// their own logo/theme-toggle, and a "Log in" link makes no sense while
// already on /login (same for "Get started" on /signup).
function isAuthRoute(pathname: string): boolean {
  return (
    pathname.startsWith("/login") ||
    pathname.startsWith("/signup") ||
    pathname.startsWith("/auth")
  );
}

// Longest-prefix match → the label shown in the top bar. Sub-tab routes resolve
// to their section (e.g. /agent-teams → "Coworkers"); the SectionTabs strip
// below the bar handles the finer level.
const TITLES: [string, string][] = [
  ["/home", "Home"],
  ["/coworkers", "Coworkers"],
  ["/agent-teams", "Coworkers"],
  ["/tasks", "Tasks"],
  ["/approvals", "Tasks"],
  ["/conversations", "Conversations"],
  ["/knowledge", "Knowledge"],
  ["/memory", "Knowledge"],
  ["/artifacts", "Knowledge"],
  ["/projects", "Projects"],
  ["/workflows", "Workflows"],
  ["/marketplace", "Marketplace"],
  ["/observability/usage", "Usage"],
  ["/observability/audit", "Audit log"],
  ["/governance", "Governance"],
  ["/evolution", "Adaptive collaboration"],
  ["/voice", "Live voice"],
  ["/creator", "Creator payouts"],
  ["/settings/organization", "Organization"],
  ["/settings/integrations", "Integrations"],
  ["/settings/enterprise", "Enterprise controls"],
  ["/settings/provider-credentials", "Model providers"],
  ["/settings/mfa", "Security"],
  ["/settings/workspace", "Workspace"],
  ["/settings", "Settings"],
];

function routeTitle(pathname: string): string {
  const match = TITLES.filter(([prefix]) => pathname === prefix || pathname.startsWith(`${prefix}/`)).sort(
    (a, b) => b[0].length - a[0].length,
  )[0];
  return match?.[1] ?? "Deep-Foundry";
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [isAuthed, setIsAuthed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    // localStorage is client-only, so auth is resolved post-mount and
    // re-checked per route to reflect login/logout without a full reload.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsAuthed(getTokens() !== null);
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!getTokens()) return;
    void (async () => {
      try {
        setUser(await apiFetch<User>("/me"));
      } catch {
        // The mobile header falls back to a generic label without /me.
      }
    })();
  }, [isAuthed]);

  // Auth pages render full-bleed with no shared chrome at all.
  if (isAuthRoute(pathname)) {
    return <>{children}</>;
  }

  // Marketing home: a sticky, translucent top bar over the landing content.
  if (isMarketingRoute(pathname)) {
    return (
      <div className="flex min-h-full flex-col">
        <header className="sticky top-0 z-40 border-b border-border/60 bg-background/70 backdrop-blur-xl">
          <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
            <Link href="/" aria-label="Deep-Foundry home" className="shrink-0">
              <Wordmark />
            </Link>
            <nav className="hidden items-center gap-1 md:flex">
              <a
                href="#how-it-works"
                className="rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                How it works
              </a>
              <a
                href="#capabilities"
                className="rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                Capabilities
              </a>
              <a
                href="#control"
                className="rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                Control
              </a>
            </nav>
            <div className="flex items-center gap-1.5">
              <ThemeToggle variant="icon" />
              <Button asChild variant="ghost" className="h-9 px-3">
                <Link href="/login">Log in</Link>
              </Button>
              <Button asChild className="h-9 px-4">
                <Link href="/signup">Get started</Link>
              </Button>
            </div>
          </div>
        </header>
        <main className="flex flex-1 flex-col">{children}</main>
      </div>
    );
  }

  // The signed-in footer (theme row + identity + log out) is rendered by
  // SidebarUser inside AppSidebar — the shell adds no footer of its own,
  // or the sidebar ends up with two theme toggles and two account rows.
  const accountLabel = user?.display_name || user?.email?.split("@")[0] || "Account";
  const accountInitial = accountLabel.charAt(0).toUpperCase();

  // App pages: fixed sidebar (desktop) + slide-over (mobile) + topbar.
  return (
    <div className="flex h-svh overflow-hidden">
      {/* Desktop sidebar */}
      <aside className="hidden h-svh w-[266px] shrink-0 flex-col border-r border-sidebar-border bg-sidebar lg:flex">
        <AppSidebar />
      </aside>

      {/* Mobile slide-over */}
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0 bg-foreground/30 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 flex w-72 max-w-[85%] flex-col border-r border-sidebar-border bg-sidebar shadow-xl">
            <div className="flex justify-end px-3 pt-3">
              <Button variant="ghost" size="icon" onClick={() => setMobileOpen(false)} aria-label="Close">
                <XIcon className="size-5" />
              </Button>
            </div>
            <AppSidebar onNavigate={() => setMobileOpen(false)} />
          </div>
        </div>
      ) : null}

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="z-30 flex min-h-14 items-center gap-1.5 border-b border-border bg-background px-3 lg:hidden">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
          >
            <MenuIcon className="size-5" />
          </Button>
          <h1 className="truncate text-sm font-semibold tracking-tight text-foreground">
            {routeTitle(pathname)}
          </h1>
          <div className="flex-1" />
          {isAuthed ? (
            <div className="flex items-center gap-0.5">
              <NotificationBell />
              <Link
                href="/settings/workspace"
                aria-label="Account and settings"
                className="ml-1 flex size-8 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary ring-1 ring-inset ring-primary/15 transition-colors hover:bg-primary/15"
              >
                {accountInitial}
              </Link>
            </div>
          ) : (
            <Button asChild size="sm">
              <Link href="/login">Log in</Link>
            </Button>
          )}
        </header>
        <SectionTabs />
        <main className="fd-scroll flex min-h-0 flex-1 flex-col overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
