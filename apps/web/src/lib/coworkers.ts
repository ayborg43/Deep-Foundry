// Shared display constants for the Coworkers screens (Milestone 3).
// Kept as plain lookups, not a form/state abstraction — see AGENTS.md scope
// notes for Milestone 3.

import type { ModelId, RiskClassification } from "./types";

export const MODEL_OPTIONS: { id: ModelId; label: string }[] = [
  { id: "deepseek-4", label: "DeepSeek 4" },
];

export const MODEL_LABELS: Record<ModelId, string> = {
  "deepseek-4": "DeepSeek 4",
};

export const MODEL_SHORT_LABELS: Record<ModelId, string> = {
  "deepseek-4": "DeepSeek 4",
};

// Risk is a trust-relevant, scannable signal (UI_GUIDELINES.md §3.2/§3.4) —
// color-coded but never color-only (always paired with the text label).
export const RISK_BADGE_CLASS: Record<RiskClassification, string> = {
  safe: "border-transparent bg-emerald-100 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-400",
  sensitive:
    "border-transparent bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-400",
  dangerous:
    "border-transparent bg-destructive/10 text-destructive dark:bg-destructive/20",
};

export const RISK_LABELS: Record<RiskClassification, string> = {
  safe: "Safe",
  sensitive: "Sensitive",
  dangerous: "Dangerous",
};
