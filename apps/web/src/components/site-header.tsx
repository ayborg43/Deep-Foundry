"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ChevronDownIcon, MenuIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import { clearTokens, getTokens } from "@/lib/auth";
import { NotificationBell } from "@/components/notification-bell";

export function SiteHeader() {
  const pathname = usePathname();
  const router = useRouter();
  // Re-checked on every route change since there's no global auth context
  // (out of scope for Milestone 1) — this is a bare-minimum, not a
  // reactive session store.
  const [isAuthed, setIsAuthed] = useState(false);

  useEffect(() => {
    // Reads localStorage, so it can only run post-mount (server has no
    // session to check); re-run per pathname to pick up login/logout that
    // happened on the previous page without a full reload.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsAuthed(getTokens() !== null);
  }, [pathname]);

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

  return (
    <header className="border-b">
      <div className="mx-auto flex min-h-14 max-w-6xl items-center justify-between gap-3 px-4 py-2">
        <Link href="/" className="font-heading text-sm font-semibold">
          Agentarium
        </Link>
        <nav className="flex items-center gap-2 text-sm" aria-label="Primary navigation">
          {isAuthed ? (
            <>
              <Link href="/coworkers" className="hidden min-h-11 items-center text-muted-foreground hover:text-foreground sm:flex">
                Coworkers
              </Link>
              <Link href="/agent-teams" className="hidden min-h-11 items-center text-muted-foreground hover:text-foreground md:flex">
                Teams
              </Link>
              <Link href="/workflows" className="hidden min-h-11 items-center text-muted-foreground hover:text-foreground md:flex">
                Workflows
              </Link>
              <Link href="/marketplace" className="hidden min-h-11 items-center text-muted-foreground hover:text-foreground lg:flex">
                Marketplace
              </Link>
              <Link href="/tasks" className="hidden min-h-11 items-center text-muted-foreground hover:text-foreground sm:flex">
                Tasks
              </Link>
              <NotificationBell />
              <details className="relative">
                <summary className="flex min-h-11 cursor-pointer list-none items-center gap-1 rounded-md px-2 text-muted-foreground hover:bg-muted hover:text-foreground"><MenuIcon className="size-4 sm:hidden" /><span className="hidden sm:inline">More</span><ChevronDownIcon className="hidden size-3 sm:block" /></summary>
                <div className="absolute right-0 z-50 mt-1 grid w-56 gap-1 rounded-md border bg-background p-2 shadow-lg">
                  <Link href="/coworkers" className="rounded px-3 py-2 hover:bg-muted sm:hidden">Coworkers</Link>
                  <Link href="/agent-teams" className="rounded px-3 py-2 hover:bg-muted md:hidden">Agent teams</Link>
                  <Link href="/workflows" className="rounded px-3 py-2 hover:bg-muted md:hidden">Workflows</Link>
                  <Link href="/marketplace" className="rounded px-3 py-2 hover:bg-muted lg:hidden">Marketplace</Link>
                  <Link href="/tasks" className="rounded px-3 py-2 hover:bg-muted sm:hidden">Tasks</Link>
                  <Link href="/approvals" className="rounded px-3 py-2 hover:bg-muted">Approvals</Link>
                  <Link href="/memory" className="rounded px-3 py-2 hover:bg-muted">Memory</Link>
                  <Link href="/knowledge" className="rounded px-3 py-2 hover:bg-muted">Knowledge</Link>
                  <Link href="/artifacts" className="rounded px-3 py-2 hover:bg-muted">Artifacts</Link>
                  <Link href="/evolution" className="rounded px-3 py-2 hover:bg-muted">Adaptive collaboration</Link>
                  <Link href="/voice" className="rounded px-3 py-2 hover:bg-muted">Live voice</Link>
                  <Link href="/governance" className="rounded px-3 py-2 hover:bg-muted">Governance</Link>
                  <Link href="/creator" className="rounded px-3 py-2 hover:bg-muted">Creator payouts</Link>
                  <Link href="/observability/usage" className="rounded px-3 py-2 hover:bg-muted">Usage</Link>
                  <Link href="/observability/audit" className="rounded px-3 py-2 hover:bg-muted">Audit log</Link>
                  <div className="my-1 border-t" />
                  <Link href="/settings/workspace" className="rounded px-3 py-2 hover:bg-muted">Workspace</Link>
                  <Link href="/settings/organization" className="rounded px-3 py-2 hover:bg-muted">Organization</Link>
                  <Link href="/settings/integrations" className="rounded px-3 py-2 hover:bg-muted">Integrations</Link>
                  <Link href="/settings/enterprise" className="rounded px-3 py-2 hover:bg-muted">Enterprise controls</Link>
                  <Link href="/settings/provider-credentials" className="rounded px-3 py-2 hover:bg-muted">Model providers</Link>
                  <Link href="/settings/mfa" className="rounded px-3 py-2 hover:bg-muted">Security</Link>
                </div>
              </details>
              <Button type="button" variant="outline" size="sm" onClick={handleLogout}>
                Log out
              </Button>
            </>
          ) : (
            <>
              <Link href="/login" className="text-muted-foreground hover:text-foreground">
                Log in
              </Link>
              <Link href="/signup" className="text-muted-foreground hover:text-foreground">
                Sign up
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
