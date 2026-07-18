import { cn } from "@/lib/utils";

// Deep-Foundry brand mark. A small "constellation" — one lead node linked to
// three coworkers — nods to the product (agents + teams) without being literal.
// Self-contained SVG so it stays crisp at any size and needs no asset pipeline.
// The handoff's warm foundry line sits inside a high-contrast ink tile.
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      role="img"
      aria-label="Deep-Foundry"
      className={cn("size-7 shrink-0", className)}
    >
      <rect width="32" height="32" rx="8" className="fill-foreground" />
      <path
        d="M6.5 25 11 10.5l5.2 8.1L20 7l5.5 18"
        className="stroke-primary"
        strokeWidth="2.35"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
}

// Mark + wordmark lockup for headers and nav. `href` makes the whole lockup a
// link when provided (the caller supplies the Link wrapper).
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <LogoMark />
      <span className="text-[0.9375rem] font-semibold tracking-tight text-foreground">
        Deep-Foundry
      </span>
    </span>
  );
}
