// True when the browser tab is backgrounded. Polling loops skip their fetch
// while hidden so a tab left open in the background doesn't keep hammering the
// API; they resume on the next tick once the tab is visible again.
export function tabHidden(): boolean {
  return typeof document !== "undefined" && document.hidden;
}

// Run `fn` whenever the tab becomes visible again. Mobile browsers throttle or
// suspend polling intervals while the app is backgrounded, so on return the
// next tick can be far off — without this, users have to refresh to see new
// data (e.g. a pending approval). Returns a cleanup function.
export function onVisible(fn: () => void): () => void {
  if (typeof document === "undefined") return () => {};
  const handler = () => {
    if (!document.hidden) fn();
  };
  document.addEventListener("visibilitychange", handler);
  return () => document.removeEventListener("visibilitychange", handler);
}
