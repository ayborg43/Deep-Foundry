"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { MenuIcon, XIcon, LogOutIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { AppSidebar } from "@/components/app-sidebar";
import { SectionTabs } from "@/components/section-tabs";
import { NotificationBell } from "@/components/notification-bell";
import { Wordmark } from "@/components/logo";
import { apiFetch } from "@/lib/api";
import { clearTokens, getTokens, getWorkspaceId } from "@/lib/auth";
import type { User, Workspace } from "@/lib/types";

// Routes that render without the app chrome (marketing + auth).
function isPublicRoute(pathname: string): boolean {
  return (
    pathname === "/" ||
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
  const router = useRouter();
  const [isAuthed, setIsAuthed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const [workspaceName, setWorkspaceName] = useState<string>("");

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
        // Footer falls back to a generic label without /me.
      }
      try {
        const id = await getWorkspaceId();
        if (id) {
          const ws = await apiFetch<Workspace>(`/workspaces/${id}`);
          setWorkspaceName(ws.name);
        }
      } catch {
        // Workspace label is optional.
      }
    })();
  }, [isAuthed]);

  async function handleLogout() {
    const tokens = getTokens();
    try {
      if (tokens?.refresh) {
        await apiFetch("/auth/logout", {
          method: "POST",
          body: JSON.stringify({ refresh: tokens.refresh }),
        });
      }
    } catch {
      // Best-effort: clear the local session regardless of API outcome.
    } finally {
      clearTokens();
      setIsAuthed(false);
      router.push("/login");
    }
  }

  // Public / auth pages: a slim centered top bar, no sidebar.
  if (isPublicRoute(pathname)) {
    return (
      <div className="flex min-h-full flex-col">
        <header className="border-b border-border/70">
          <div className="mx-auto flex min-h-14 max-w-6xl items-center justify-between gap-3 px-4">
            <Link href="/" aria-label="Deep-Foundry home">
              <Wordmark />
            </Link>
            <nav className="flex items-center gap-1 text-sm">
              <Button asChild variant="ghost" size="sm">
                <Link href="/login">Log in</Link>
              </Button>
              <Button asChild size="sm">
                <Link href="/signup">Get started</Link>
              </Button>
            </nav>
          </div>
        </header>
        <main className="flex flex-1 flex-col">{children}</main>
      </div>
    );
  }

  const accountLabel = user?.display_name || user?.email?.split("@")[0] || "Account";
  const accountInitial = accountLabel.charAt(0).toUpperCase();
  const accountFooter = (
    <div className="border-t border-sidebar-border p-2.5">
      <div className="flex items-center gap-2.5 rounded-lg px-2 py-1.5">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary text-xs font-semibold text-primary-foreground">
          {accountInitial}
        </span>
        <div className="flex min-w-0 flex-col">
          <span className="truncate text-sm font-medium leading-tight">{accountLabel}</span>
          {workspaceName ? (
            <span className="truncate text-xs text-muted-foreground leading-tight">{workspaceName}</span>
          ) : null}
        </div>
        <button
          type="button"
          onClick={handleLogout}
          aria-label="Log out"
          className="ml-auto flex size-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-sidebar-accent/60 hover:text-foreground"
        >
          <LogOutIcon className="size-4" />
        </button>
      </div>
    </div>
  );

  // App pages: fixed sidebar (desktop) + slide-over (mobile) + topbar.
  return (
    <div className="flex min-h-full">
      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-svh w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar lg:flex">
        <AppSidebar />
        {isAuthed ? accountFooter : null}
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
            {isAuthed ? accountFooter : null}
          </div>
        </div>
      ) : null}

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex min-h-14 items-center gap-1.5 border-b border-border/70 bg-background/80 px-3 backdrop-blur-md sm:px-4">
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
        <main className="flex flex-1 flex-col">{children}</main>
      </div>
    </div>
  );
}
