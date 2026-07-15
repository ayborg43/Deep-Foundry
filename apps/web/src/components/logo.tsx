import { cn } from "@/lib/utils";

// Deep-Foundry brand mark. A small "constellation" — one lead node linked to
// three coworkers — nods to the product (agents + teams) without being literal.
// Self-contained SVG so it stays crisp at any size and needs no asset pipeline.
// The tile carries the DeepSeek-blue primary; the glyph is the tile foreground.
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      role="img"
      aria-label="Deep-Foundry"
      className={cn("size-7 shrink-0", className)}
    >
      <rect width="32" height="32" rx="8" className="fill-primary" />
      <g
        className="stroke-primary-foreground"
        strokeWidth="1.75"
        strokeLinecap="round"
        fill="none"
      >
        {/* links from the lead node to each coworker node */}
        <path d="M16 15.5 L9.5 10" />
        <path d="M16 15.5 L23 11" />
        <path d="M16 15.5 L15.5 23" />
      </g>
      <g className="fill-primary-foreground">
        <circle cx="16" cy="15.5" r="3" />
        <circle cx="9.5" cy="10" r="2" />
        <circle cx="23" cy="11" r="2" />
        <circle cx="15.5" cy="23" r="2" />
      </g>
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
