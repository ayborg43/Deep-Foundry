// Theme preference: light (default), dark, or follow the OS ("system").
// The stored value is read both here and by the tiny inline script in
// layout.tsx that sets the `.dark` class before first paint (no flash).

export type ThemePref = "light" | "dark" | "system";

export const THEME_KEY = "deep-foundry.theme";

export function getThemePref(): ThemePref {
  if (typeof window === "undefined") return "light";
  const value = window.localStorage.getItem(THEME_KEY);
  // Default is light — an unset or unrecognized value resolves to it.
  return value === "dark" || value === "system" ? value : "light";
}

export function prefersDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

export function isDark(pref: ThemePref): boolean {
  return pref === "dark" || (pref === "system" && prefersDark());
}

// Persist the preference and apply it to <html> immediately.
export function applyThemePref(pref: ThemePref): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(THEME_KEY, pref);
  document.documentElement.classList.toggle("dark", isDark(pref));
}
