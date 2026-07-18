import {
  ArrowUpIcon,
  CheckIcon,
  MicIcon,
  PlusIcon,
  ShieldCheckIcon,
  SparklesIcon,
} from "lucide-react";

// A crafted, static illustration of the real product surface — composer,
// a running background task, and an approval gate — assembled from the same
// tokens the live app uses so the landing shows the actual thing, not a
// generic hero graphic. Decorative: the surrounding copy carries the meaning,
// so the whole mock is hidden from assistive tech.
export function HeroMockup() {
  return (
    <div aria-hidden="true" className="relative select-none">
      {/* Floating accent chips add depth around the window. */}
      <div className="chip-float absolute -left-4 top-10 z-20 hidden items-center gap-2 rounded-xl border border-border bg-card/95 px-3 py-2 shadow-[var(--shadow-lg)] backdrop-blur-sm sm:flex">
        <span className="flex size-6 items-center justify-center rounded-full bg-primary/12 text-primary">
          <CheckIcon className="size-3.5" />
        </span>
        <span className="text-xs font-medium">Briefing delivered</span>
      </div>

      <div
        className="chip-float absolute -right-3 bottom-14 z-20 hidden items-center gap-2 rounded-xl border border-border bg-card/95 px-3 py-2 shadow-[var(--shadow-lg)] backdrop-blur-sm sm:flex"
        style={{ animationDelay: "2.2s" }}
      >
        <span className="flex size-6 items-center justify-center rounded-full bg-primary/12 text-primary">
          <SparklesIcon className="size-3.5" />
        </span>
        <span className="text-xs font-medium">3 coworkers online</span>
      </div>

      {/* The product window. */}
      <div className="relative overflow-hidden rounded-2xl border border-border bg-card shadow-[var(--shadow-lg)] ring-1 ring-foreground/5">
        {/* Title bar */}
        <div className="flex items-center gap-2 border-b border-border/70 px-4 py-3">
          <span className="flex gap-1.5">
            <span className="size-2.5 rounded-full bg-foreground/15" />
            <span className="size-2.5 rounded-full bg-foreground/15" />
            <span className="size-2.5 rounded-full bg-foreground/15" />
          </span>
          <span className="ml-2 text-xs font-medium text-muted-foreground">
            deep-foundry.app
          </span>
          <span className="ml-auto text-[0.7rem] font-medium text-muted-foreground">
            DeepSeek-V3
          </span>
        </div>

        <div className="flex flex-col gap-4 p-4">
          {/* Composer */}
          <div className="rounded-xl border border-border bg-background p-3 shadow-[var(--shadow-sm)]">
            <p className="px-1 pt-1 pb-3 text-[0.9rem] leading-relaxed text-foreground">
              Draft the Q3 board update from our metrics and last month&apos;s
              notes.
            </p>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="flex size-7 items-center justify-center rounded-full text-muted-foreground">
                  <PlusIcon className="size-4" />
                </span>
                <span className="flex items-center rounded-full bg-secondary p-0.5 text-xs font-medium">
                  <span className="rounded-full px-2.5 py-1 text-muted-foreground">
                    Chat
                  </span>
                  <span className="rounded-full bg-background px-2.5 py-1 text-foreground shadow-[var(--shadow-sm)]">
                    Cowork
                  </span>
                </span>
              </div>
              <div className="flex items-center gap-2">
                <MicIcon className="size-4 text-muted-foreground" />
                <span className="flex size-7 items-center justify-center rounded-full bg-primary text-primary-foreground">
                  <ArrowUpIcon className="size-4" />
                </span>
              </div>
            </div>
          </div>

          {/* Running task */}
          <div className="rounded-xl border border-border bg-background/60 p-3">
            <div className="flex items-center gap-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/12 text-xs font-semibold text-primary">
                AT
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[0.8rem] font-medium">
                  Atlas · Research
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  Gathering sources · step 2 of 4
                </p>
              </div>
              <span className="flex items-center gap-1.5 rounded-full bg-primary/10 px-2 py-1 text-[0.7rem] font-medium text-primary">
                <span className="size-1.5 animate-pulse rounded-full bg-primary" />
                Running
              </span>
            </div>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-secondary">
              <div className="h-full w-1/2 rounded-full bg-primary" />
            </div>
          </div>

          {/* Approval gate */}
          <div className="rounded-xl border border-primary/25 bg-primary/[0.06] p-3">
            <div className="flex items-center gap-3">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
                <ShieldCheckIcon className="size-4" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[0.8rem] font-medium">
                  Send email to the board
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  Vega · Ops needs your approval
                </p>
              </div>
              <span className="flex items-center gap-1.5">
                <span className="rounded-lg border border-border bg-background px-2.5 py-1 text-[0.7rem] font-medium text-muted-foreground">
                  Deny
                </span>
                <span className="rounded-lg bg-primary px-2.5 py-1 text-[0.7rem] font-medium text-primary-foreground">
                  Approve
                </span>
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
