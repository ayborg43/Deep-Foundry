"use client";

import { useEffect, useState } from "react";
import { MonitorIcon, MoonIcon, SunIcon, type LucideIcon } from "lucide-react";

import { applyThemePref, getThemePref, isDark, type ThemePref } from "@/lib/theme";

const OPTIONS: { value: ThemePref; label: string; icon: LucideIcon }[] = [
  { value: "light", label: "Light", icon: SunIcon },
  { value: "system", label: "System", icon: MonitorIcon },
  { value: "dark", label: "Dark", icon: MoonIcon },
];

// Shared: resolves the stored pref post-mount and keeps it synced while
// following the OS. Both the segmented and icon variants need this.
function useThemePref() {
  const [pref, setPref] = useState<ThemePref>("light");

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPref(getThemePref());
  }, []);

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

  return { pref, choose };
}

export function ThemeToggle({
  className = "",
  variant = "segmented",
}: {
  className?: string;
  /** "segmented" (default): light/system/dark, three visible options.
   *  "icon": a single button that toggles light ↔ dark.
   *  "row": a full-width labeled pill ("Dark mode" / "Light mode"). */
  variant?: "segmented" | "icon" | "row";
}) {
  const { pref, choose } = useThemePref();

  if (variant === "row") {
    const dark = isDark(pref);
    return (
      <button
        type="button"
        onClick={() => choose(dark ? "light" : "dark")}
        className={`flex w-full items-center gap-2.5 rounded-[11px] border border-border bg-card px-3 py-2 text-[0.8125rem] font-medium text-muted-foreground shadow-[var(--shadow-sm)] transition-colors hover:text-foreground ${className}`}
      >
        {dark ? <SunIcon className="size-4" /> : <MoonIcon className="size-4" />}
        {dark ? "Light mode" : "Dark mode"}
      </button>
    );
  }

  if (variant === "icon") {
    const dark = isDark(pref);
    return (
      <button
        type="button"
        onClick={() => choose(dark ? "light" : "dark")}
        aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
        title={dark ? "Switch to light theme" : "Switch to dark theme"}
        className={`flex size-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground ${className}`}
      >
      {dark ? <SunIcon className="size-4" /> : <MoonIcon className="size-4" />}
      </button>
    );
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
