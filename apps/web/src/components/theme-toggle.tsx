"use client";

import { useEffect, useState } from "react";
import { MonitorIcon, MoonIcon, SunIcon, type LucideIcon } from "lucide-react";

import { applyThemePref, getThemePref, isDark, type ThemePref } from "@/lib/theme";

const OPTIONS: { value: ThemePref; label: string; icon: LucideIcon }[] = [
  { value: "light", label: "Light", icon: SunIcon },
  { value: "system", label: "System", icon: MonitorIcon },
  { value: "dark", label: "Dark", icon: MoonIcon },
];

export function ThemeToggle({ className = "" }: { className?: string }) {
  const [pref, setPref] = useState<ThemePref>("light");

  // localStorage is client-only, so the real preference resolves post-mount.
  // The theme itself is already correct (the inline script set it before
  // paint); this only syncs which segment reads as active.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPref(getThemePref());
  }, []);

  // While following the OS, re-apply when the OS theme flips under us.
  useEffect(() => {
    if (pref !== "system") return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => document.documentElement.classList.toggle("dark", isDark("system"));
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, [pref]);

  function choose(next: ThemePref) {
    setPref(next);
    applyThemePref(next);
  }

  return (
    <div
      role="radiogroup"
      aria-label="Color theme"
      className={`flex items-center gap-0.5 rounded-lg border border-border bg-muted/50 p-0.5 ${className}`}
    >
      {OPTIONS.map(({ value, label, icon: Icon }) => {
        const active = pref === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            onClick={() => choose(value)}
            className={`flex flex-1 items-center justify-center rounded-md py-1.5 transition-colors ${
              active
                ? "bg-background text-foreground shadow-[var(--shadow-sm)]"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Icon className="size-4" />
          </button>
        );
      })}
    </div>
  );
}
