"use client";

import { useEffect, useRef, useState } from "react";
import { Building2, Check, ChevronsUpDown, PlusIcon, UserRound } from "lucide-react";

import { NewOrganizationDialog } from "@/components/new-organization-dialog";
import { apiFetch } from "@/lib/api";
import { getStoredWorkspaceId, getTokens, setWorkspaceId } from "@/lib/auth";
import type { Workspace } from "@/lib/types";

function isOrg(workspace: Workspace) {
  return workspace.type === "organization";
}

export function WorkspaceSwitcher() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!getTokens()) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setActiveId(getStoredWorkspaceId());
    void (async () => {
      try {
        const rows = await apiFetch<Workspace[]>("/workspaces");
        setWorkspaces(rows);
        setActiveId((current) => current ?? rows[0]?.id ?? null);
      } catch {
        // Switcher is supplementary; if the list can't load it stays hidden.
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

  const active = workspaces.find((w) => w.id === activeId) ?? workspaces[0];

  function switchTo(id: string) {
    setOpen(false);
    if (id === active?.id) return;
    setWorkspaceId(id);
    // Full reload so every page re-scopes its data to the new workspace —
    // pages read the active id via getWorkspaceId() on mount.
    window.location.assign("/home");
  }

  // Until the list loads there's nothing meaningful to switch between.
  if (workspaces.length === 0 || !active) return null;

  const ActiveIcon = isOrg(active) ? Building2 : UserRound;

  return (
    <div ref={ref} className="relative px-3 pb-2">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex w-full items-center gap-2.5 rounded-lg border border-sidebar-border bg-sidebar-accent/40 px-2.5 py-2 text-left transition-colors hover:bg-sidebar-accent/70"
      >
        <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary/12 text-primary">
          <ActiveIcon className="size-4" />
        </span>
        <span className="flex min-w-0 flex-col">
          <span className="truncate text-[0.8125rem] font-semibold leading-tight">{active.name}</span>
          <span className="truncate text-[0.6875rem] leading-tight text-muted-foreground">
            {isOrg(active) ? "Organization" : "Personal"}
          </span>
        </span>
        <ChevronsUpDown className="ml-auto size-3.5 shrink-0 text-muted-foreground" />
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute inset-x-3 top-full z-50 mt-1 overflow-hidden rounded-lg border border-border bg-popover p-1 shadow-[var(--shadow-lg)]"
        >
          <p className="px-2 pb-1 pt-1.5 text-[0.6875rem] font-semibold uppercase tracking-wider text-muted-foreground/70">
            Switch workspace
          </p>
          <ul className="grid max-h-64 gap-0.5 overflow-y-auto">
            {workspaces.map((workspace) => {
              const Icon = isOrg(workspace) ? Building2 : UserRound;
              const selected = workspace.id === active.id;
              return (
                <li key={workspace.id}>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => switchTo(workspace.id)}
                    className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent"
                  >
                    <Icon className="size-4 shrink-0 text-muted-foreground" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate leading-tight">{workspace.name}</span>
                      <span className="block truncate text-[0.6875rem] leading-tight text-muted-foreground">
                        {isOrg(workspace) ? "Organization" : "Personal"}
                      </span>
                    </span>
                    {selected ? <Check className="size-4 shrink-0 text-primary" /> : null}
                  </button>
                </li>
              );
            })}
          </ul>
          <div className="mt-1 border-t border-border pt-1">
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                setCreateOpen(true);
              }}
              className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm font-medium text-primary transition-colors hover:bg-accent"
            >
              <PlusIcon className="size-4 shrink-0" />
              New organization
            </button>
          </div>
        </div>
      ) : null}

      <NewOrganizationDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
