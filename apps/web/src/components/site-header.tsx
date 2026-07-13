"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import { clearTokens, getTokens } from "@/lib/auth";

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
      <div className="mx-auto flex h-14 max-w-4xl items-center justify-between px-4">
        <Link href="/" className="font-heading text-sm font-semibold">
          Agentarium
        </Link>
        <nav className="flex items-center gap-4 text-sm">
          {isAuthed ? (
            <>
              <Link
                href="/settings/workspace"
                className="text-muted-foreground hover:text-foreground"
              >
                Workspace
              </Link>
              <Link
                href="/settings/provider-credentials"
                className="text-muted-foreground hover:text-foreground"
              >
                Provider Credentials
              </Link>
              <Link
                href="/settings/mfa"
                className="text-muted-foreground hover:text-foreground"
              >
                MFA
              </Link>
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
