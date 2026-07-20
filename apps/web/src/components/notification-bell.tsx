"use client";

import Link from "next/link";
import { BellIcon } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import type { Notification } from "@/lib/types";

export function NotificationBell() {
  const [items, setItems] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        setItems(await apiFetch<Notification[]>("/notifications?unread=true"));
      } catch {
        // Header notifications are supplementary; route-level errors remain visible.
      }
    }
    void load();
    const timer = window.setInterval(load, 30_000);
    return () => window.clearInterval(timer);
  }, []);

  async function markRead(notification: Notification) {
    await apiFetch(`/notifications/${notification.id}/read`, { method: "PATCH" });
    setItems((current) => current.filter((item) => item.id !== notification.id));
    setOpen(false);
  }

  return (
    <div className="relative">
      <Button
        type="button"
        size="icon-sm"
        variant="ghost"
        aria-label={`${items.length} unread notifications`}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <BellIcon />
        {items.length ? (
          <span className="absolute -right-1 -top-1 min-w-4 rounded-full bg-destructive px-1 text-center text-[10px] text-white">
            {Math.min(items.length, 99)}
          </span>
        ) : null}
      </Button>
      {open ? (
        <div className="absolute right-0 top-10 z-50 w-80 rounded-xl border border-border bg-popover p-1.5 shadow-[var(--shadow-lg)]">
          <p className="px-2 py-1 text-xs font-medium text-muted-foreground">Notifications</p>
          {items.length === 0 ? (
            <p className="px-2 py-4 text-sm text-muted-foreground">You&apos;re all caught up.</p>
          ) : (
            items.slice(0, 8).map((item) => {
              const href =
                item.type === "approval_requested" ? "/approvals" :
                item.type === "research_completed" && item.payload.research_run_id ? `/research/${item.payload.research_run_id}` :
                (item.type === "website_changed" || item.type === "monitor_failed") && item.payload.monitor_id ? `/research/monitors/${item.payload.monitor_id}` :
                item.payload.task_id ? `/tasks/${item.payload.task_id}` : "/home";
              const detail =
                item.type === "approval_requested"
                  ? `Approval needed for ${item.payload.tool_name ?? "a tool"}`
                  : item.type === "research_completed"
                    ? "Research report is ready"
                    : item.type === "website_changed"
                      ? item.payload.change_summary ?? "Meaningful website changes detected"
                      : item.type === "monitor_failed"
                        ? "Website check failed"
                        : `Task ${item.payload.status ?? "updated"}`;
              return (
                <Link
                  key={item.id}
                  href={href}
                  className="block rounded-md px-2 py-2 hover:bg-muted"
                  onClick={() => void markRead(item)}
                >
                  <p className="text-sm font-medium">{item.payload.title ?? "Task update"}</p>
                  <p className="text-xs text-muted-foreground">{detail}</p>
                </Link>
              );
            })
          )}
        </div>
      ) : null}
    </div>
  );
}
