// True when the browser tab is backgrounded. Polling loops skip their fetch
// while hidden so a tab left open in the background doesn't keep hammering the
// API; they resume on the next tick once the tab is visible again.
export function tabHidden(): boolean {
  return typeof document !== "undefined" && document.hidden;
}
