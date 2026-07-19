"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, LogOut } from "lucide-react";

import { ThemeToggle } from "@/components/theme-toggle";
import { apiFetch } from "@/lib/api";
import { clearTokens, getStoredWorkspaceId, getTokens } from "@/lib/auth";
import type { User, Workspace } from "@/lib/types";

// Sidebar footer: theme row + the signed-in identity ("Sarah Okonkwo,
// Owner · Northwind") with a small menu for signing out.
export function SidebarUser() {
  const [user, setUser] = useState<User | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!getTokens()) return;
    void (async () => {
      try {
        const me = await apiFetch<User>("/me");
        setUser(me);
        const workspaces = await apiFetch<Workspace[]>("/workspaces");
        const activeId = getStoredWorkspaceId();
        setWorkspace(workspaces.find((w) => w.id === activeId) ?? workspaces[0] ?? null);
      } catch {
        // Footer is decoration; the sidebar works without it.
      }
    })();
  }, []);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

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
      // Best effort — clearing local tokens signs this device out regardless.
    }
    clearTokens();
    window.location.assign("/login");
  }

  if (!user) return null;

  const displayName = user.display_name || user.email.split("@")[0];
  const role =
    workspace && workspace.owner_id === user.id ? "Owner" : workspace ? "Member" : null;

  return (
    <div className="border-t border-sidebar-border px-3 pb-3 pt-2.5">
      <ThemeToggle variant="row" />

      <div ref={ref} className="relative mt-2">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-haspopup="menu"
          aria-expanded={open}
          className="flex w-full items-center gap-2.5 rounded-[11px] px-2 py-1.5 text-left transition-colors hover:bg-sidebar-accent"
        >
          {user.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={user.avatar_url}
              alt=""
              className="size-8 shrink-0 rounded-full object-cover"
            />
          ) : (
            <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-semibold uppercase text-muted-foreground">
              {displayName.slice(0, 1)}
            </span>
          )}
          <span className="flex min-w-0 flex-col">
            <span className="truncate text-[0.8125rem] font-semibold leading-tight">
              {displayName}
            </span>
            <span className="truncate text-[0.6875rem] leading-tight text-muted-foreground">
              {role ? `${role}${workspace ? ` · ${workspace.name}` : ""}` : user.email}
            </span>
          </span>
          <ChevronDown
            className={`ml-auto size-3.5 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
          />
        </button>

        {open ? (
          <div
            role="menu"
            className="absolute inset-x-0 bottom-full z-50 mb-1 overflow-hidden rounded-lg border border-border bg-popover p-1 shadow-[var(--shadow-lg)]"
          >
            <button
              type="button"
              role="menuitem"
              onClick={() => void handleLogout()}
              className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent"
            >
              <LogOut className="size-4 shrink-0 text-muted-foreground" />
              Log out
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
