import Link from "next/link";
import {
  ArrowRightIcon,
  BrainIcon,
  CheckIcon,
  ListTodoIcon,
  MicIcon,
  NetworkIcon,
  PackageIcon,
  ScrollTextIcon,
  ServerIcon,
  ShieldCheckIcon,
  SparklesIcon,
  UsersIcon,
  WorkflowIcon,
} from "lucide-react";

import { HeroMockup } from "@/components/marketing/hero-mockup";
import { NetworkBackdrop } from "@/components/marketing/network-backdrop";
import { Reveal } from "@/components/marketing/reveal";
import { Button } from "@/components/ui/button";

const STACK = [
  "DeepSeek",
  "Docker",
  "PostgreSQL",
  "Redis",
  "MinIO / S3",
  "Python sandbox",
  "Slack",
  "Google",
  "Webhooks",
];

const STEPS = [
  {
    icon: UsersIcon,
    title: "Hire a coworker",
    body: "Spin up an AI coworker with its own role, model, and tools — or start from a reviewed Marketplace pack.",
  },
  {
    icon: ListTodoIcon,
    title: "Assign the work",
    body: "Chat for a quick answer, or hand off a background task and walk away while it runs on its own.",
  },
  {
    icon: ShieldCheckIcon,
    title: "Approve & ship",
    body: "Risky steps pause for your sign-off, every action is logged, and finished work lands back with you.",
  },
];

export default function Home() {
  return (
    <div className="flex flex-1 flex-col">
      {/* ── Hero ─────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden">
        {/* Ambient constellation + blue bloom behind the hero */}
        <NetworkBackdrop className="pointer-events-none absolute inset-0 -z-10 h-full w-full opacity-[0.18] [mask-image:radial-gradient(120%_100%_at_70%_20%,black,transparent_75%)]" />
        <div
          className="pointer-events-none absolute -top-32 right-[-10%] -z-10 size-[42rem] rounded-full opacity-60 blur-3xl"
          style={{
            background:
              "radial-gradient(closest-side, color-mix(in oklch, var(--primary) 22%, transparent), transparent)",
          }}
        />

        <div className="mx-auto grid w-full max-w-6xl grid-cols-1 items-center gap-14 px-4 pt-16 pb-20 sm:px-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] lg:gap-10 lg:pt-24 lg:pb-28">
          <div className="min-w-0 max-w-xl">
            <Reveal>
              <h1 className="font-heading text-[clamp(2.5rem,5vw+1rem,4.25rem)] font-semibold leading-[1.04] tracking-[-0.03em] text-balance">
                Your AI coworkers do the work.{" "}
                <span className="text-primary">You approve what matters.</span>
              </h1>
            </Reveal>

            <Reveal delay={80}>
              <p className="mt-6 max-w-lg text-lg leading-relaxed text-muted-foreground text-pretty">
                Deep-Foundry gives you persistent AI coworkers with memory,
                tools, and human-controlled permissions. Assign a task, approve
                the risky steps, and come back to finished work — self-hosted on
                your own infrastructure.
              </p>
            </Reveal>

            <Reveal delay={160}>
              <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
                <Button asChild className="h-12 px-6 text-[0.95rem]">
                  <Link href="/signup">
                    Get started free
                    <ArrowRightIcon data-icon="inline-end" />
                  </Link>
                </Button>
                <Button
                  asChild
                  variant="outline"
                  className="h-12 px-6 text-[0.95rem]"
                >
                  <a href="#how-it-works">See how it works</a>
                </Button>
              </div>
            </Reveal>

            <Reveal delay={220}>
              <ul className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-muted-foreground">
                {[
                  "No credit card",
                  "Self-hostable",
                  "Sandboxed execution",
                ].map((item) => (
                  <li key={item} className="flex items-center gap-1.5">
                    <CheckIcon className="size-4 text-primary" />
                    {item}
                  </li>
                ))}
              </ul>
            </Reveal>
          </div>

          <Reveal delay={140} className="min-w-0 lg:pl-4">
            <HeroMockup />
          </Reveal>
        </div>
      </section>

      {/* ── Trust strip ──────────────────────────────────────────────── */}
      <section className="border-y border-border/60 bg-muted/30 py-8">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <p className="text-center text-sm text-muted-foreground">
            Runs on your infrastructure — connects to the tools you already use
          </p>
          <div className="relative mt-5 overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_8%,black_92%,transparent)]">
            <div className="marquee-track flex w-max items-center gap-10 pr-10">
              {[...STACK, ...STACK].map((name, i) => (
                <span
                  key={`${name}-${i}`}
                  className="text-base font-medium whitespace-nowrap text-foreground/70"
                >
                  {name}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── How it works ─────────────────────────────────────────────── */}
      <section id="how-it-works" className="scroll-mt-20 py-24">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <Reveal className="max-w-2xl">
            <h2 className="font-heading text-[clamp(1.9rem,3vw+0.5rem,2.75rem)] font-semibold tracking-[-0.025em] text-balance">
              From request to finished work in three moves
            </h2>
            <p className="mt-4 text-lg text-muted-foreground text-pretty">
              No prompt-engineering rituals. Hire, hand off, and stay in the
              loop only where it counts.
            </p>
          </Reveal>

          <ol className="mt-14 grid gap-8 md:grid-cols-3 md:gap-6">
            {STEPS.map((step, i) => {
              const Icon = step.icon;
              return (
                <Reveal as="li" key={step.title} delay={i * 90} className="relative">
                  {/* Through-line connecting the steps on desktop */}
                  {i < STEPS.length - 1 ? (
                    <span
                      aria-hidden
                      className="absolute top-6 left-[calc(50%+2.5rem)] hidden h-px w-[calc(100%-3rem)] bg-gradient-to-r from-border to-transparent md:block"
                    />
                  ) : null}
                  <div className="flex items-center gap-4">
                    <span className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-primary/10 text-primary ring-1 ring-primary/15">
                      <Icon className="size-5" />
                    </span>
                    <span className="font-heading text-5xl font-semibold text-foreground/10 tabular-nums">
                      {i + 1}
                    </span>
                  </div>
                  <h3 className="mt-5 font-heading text-lg font-semibold tracking-tight">
                    {step.title}
                  </h3>
                  <p className="mt-2 text-[0.95rem] leading-relaxed text-muted-foreground text-pretty">
                    {step.body}
                  </p>
                </Reveal>
              );
            })}
          </ol>
        </div>
      </section>

      {/* ── Capabilities (bento) ─────────────────────────────────────── */}
      <section id="capabilities" className="scroll-mt-20 pb-24">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <Reveal className="max-w-2xl">
            <h2 className="font-heading text-[clamp(1.9rem,3vw+0.5rem,2.75rem)] font-semibold tracking-[-0.025em] text-balance">
              Everything your team needs to delegate with confidence
            </h2>
          </Reveal>

          <div className="mt-12 grid gap-4 md:grid-cols-3">
            {/* Persistent coworkers — large, with a mini visual */}
            <Reveal className="md:col-span-2">
              <article className="flex h-full flex-col justify-between gap-6 rounded-3xl border border-border/70 bg-card/60 p-7 backdrop-blur-sm">
                <div className="max-w-md">
                  <span className="flex size-10 items-center justify-center rounded-xl bg-primary/12 text-primary">
                    <UsersIcon className="size-5" />
                  </span>
                  <h3 className="mt-4 font-heading text-xl font-semibold tracking-tight">
                    Persistent coworkers with memory
                  </h3>
                  <p className="mt-2 text-[0.95rem] leading-relaxed text-muted-foreground text-pretty">
                    Each coworker keeps its own role, model, tools, and
                    long-term memory — so it remembers your context and gets
                    sharper the more you work together.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {[
                    { initials: "AT", role: "Research" },
                    { initials: "VE", role: "Ops" },
                    { initials: "NO", role: "Support" },
                  ].map((c) => (
                    <span
                      key={c.initials}
                      className="flex items-center gap-2 rounded-full border border-border bg-background px-3 py-1.5"
                    >
                      <span className="flex size-6 items-center justify-center rounded-full bg-primary/12 text-[0.65rem] font-semibold text-primary">
                        {c.initials}
                      </span>
                      <span className="text-sm font-medium">{c.role}</span>
                    </span>
                  ))}
                </div>
              </article>
            </Reveal>

            {/* Background tasks — with progress visual */}
            <Reveal delay={80}>
              <article className="flex h-full flex-col justify-between gap-6 rounded-3xl border border-border/70 bg-card/60 p-7 backdrop-blur-sm">
                <div>
                  <span className="flex size-10 items-center justify-center rounded-xl bg-primary/12 text-primary">
                    <ListTodoIcon className="size-5" />
                  </span>
                  <h3 className="mt-4 font-heading text-xl font-semibold tracking-tight">
                    Background tasks
                  </h3>
                  <p className="mt-2 text-[0.95rem] leading-relaxed text-muted-foreground text-pretty">
                    Hand off work and walk away. It runs on its own and returns
                    a finished result.
                  </p>
                </div>
                <div className="space-y-2">
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-secondary">
                    <div className="h-full w-[68%] rounded-full bg-primary" />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Drafting report · step 3 of 4
                  </p>
                </div>
              </article>
            </Reveal>

            {/* Multi-agent teams */}
            <Reveal delay={40}>
              <article className="flex h-full flex-col gap-3 rounded-3xl border border-border/70 bg-card/60 p-7 backdrop-blur-sm">
                <span className="flex size-10 items-center justify-center rounded-xl bg-primary/12 text-primary">
                  <NetworkIcon className="size-5" />
                </span>
                <h3 className="mt-1 font-heading text-lg font-semibold tracking-tight">
                  Multi-agent teams
                </h3>
                <p className="text-[0.95rem] leading-relaxed text-muted-foreground text-pretty">
                  Group coworkers into teams that plan and hand off to each
                  other on a shared goal.
                </p>
              </article>
            </Reveal>

            {/* Knowledge & memory — large, with a mini visual */}
            <Reveal delay={120} className="md:col-span-2">
              <article className="flex h-full flex-col justify-between gap-6 rounded-3xl border border-border/70 bg-card/60 p-7 backdrop-blur-sm sm:flex-row sm:items-center">
                <div className="max-w-sm">
                  <span className="flex size-10 items-center justify-center rounded-xl bg-primary/12 text-primary">
                    <BrainIcon className="size-5" />
                  </span>
                  <h3 className="mt-4 font-heading text-xl font-semibold tracking-tight">
                    Knowledge & memory
                  </h3>
                  <p className="mt-2 text-[0.95rem] leading-relaxed text-muted-foreground text-pretty">
                    Give coworkers a knowledge base that grows with you. They
                    cite what they used, so answers stay grounded.
                  </p>
                </div>
                <ul className="w-full shrink-0 space-y-2 sm:max-w-[15rem]">
                  {["Q3 metrics.csv", "Brand guidelines", "Board notes"].map(
                    (doc) => (
                      <li
                        key={doc}
                        className="flex items-center gap-2.5 rounded-lg border border-border bg-background px-3 py-2 text-sm"
                      >
                        <ScrollTextIcon className="size-4 shrink-0 text-primary" />
                        <span className="truncate">{doc}</span>
                      </li>
                    ),
                  )}
                </ul>
              </article>
            </Reveal>

            {/* Small trio: workflows, marketplace, voice/desktop */}
            {[
              {
                icon: WorkflowIcon,
                title: "Durable workflows",
                body: "Scheduled and event-driven runs that survive restarts.",
              },
              {
                icon: PackageIcon,
                title: "Marketplace packs",
                body: "Install reviewed capability packs, or publish your own.",
              },
              {
                icon: MicIcon,
                title: "Voice & desktop",
                body: "Talk to coworkers, or grant a permission-gated desktop companion.",
              },
            ].map((cap, i) => {
              const Icon = cap.icon;
              return (
                <Reveal key={cap.title} delay={i * 70}>
                  <article className="flex h-full flex-col gap-3 rounded-3xl border border-border/70 bg-card/60 p-7 backdrop-blur-sm">
                    <span className="flex size-10 items-center justify-center rounded-xl bg-primary/12 text-primary">
                      <Icon className="size-5" />
                    </span>
                    <h3 className="mt-1 font-heading text-lg font-semibold tracking-tight">
                      {cap.title}
                    </h3>
                    <p className="text-[0.95rem] leading-relaxed text-muted-foreground text-pretty">
                      {cap.body}
                    </p>
                  </article>
                </Reveal>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── Control band ─────────────────────────────────────────────── */}
      <section id="control" className="scroll-mt-20 border-t border-border/60 bg-muted/30 py-24">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 sm:px-6 lg:grid-cols-2 lg:gap-16">
          <Reveal>
            <h2 className="font-heading text-[clamp(1.9rem,3vw+0.5rem,2.75rem)] font-semibold tracking-[-0.025em] text-balance">
              You&apos;re always the last word
            </h2>
            <p className="mt-4 text-lg leading-relaxed text-muted-foreground text-pretty">
              Autonomy without control is a liability. Deep-Foundry gates every
              risky action behind your approval, runs code in a fresh
              networkless sandbox, and writes an audit trail you can export.
            </p>
            <ul className="mt-8 space-y-4">
              {[
                {
                  icon: ShieldCheckIcon,
                  title: "Approval gates",
                  body: "Nothing risky happens without your explicit sign-off.",
                },
                {
                  icon: ServerIcon,
                  title: "Sandboxed execution",
                  body: "Every Python call runs in a fresh, resource-limited, networkless container.",
                },
                {
                  icon: ScrollTextIcon,
                  title: "Full audit trail",
                  body: "Every decision and action is logged, attributable, and exportable.",
                },
              ].map((item) => {
                const Icon = item.icon;
                return (
                  <li key={item.title} className="flex gap-3.5">
                    <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/12 text-primary">
                      <Icon className="size-4.5" />
                    </span>
                    <div>
                      <p className="font-medium">{item.title}</p>
                      <p className="text-[0.95rem] leading-relaxed text-muted-foreground text-pretty">
                        {item.body}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ul>
          </Reveal>

          {/* Crafted audit-trail visual */}
          <Reveal delay={120}>
            <div className="rounded-2xl border border-border bg-card p-5 shadow-[var(--shadow-lg)] ring-1 ring-foreground/5">
              <div className="flex items-center justify-between border-b border-border/70 pb-3">
                <p className="text-sm font-medium">Activity</p>
                <span className="text-xs text-muted-foreground">Today</span>
              </div>
              <ul className="divide-y divide-border/60">
                {[
                  {
                    label: "Read knowledge base",
                    who: "Atlas · Research",
                    state: "auto",
                  },
                  {
                    label: "Run analysis in sandbox",
                    who: "Atlas · Research",
                    state: "sandbox",
                  },
                  {
                    label: "Send email to the board",
                    who: "Vega · Ops",
                    state: "pending",
                  },
                  {
                    label: "Post summary to Slack",
                    who: "Nova · Support",
                    state: "approved",
                  },
                ].map((row) => (
                  <li key={row.label} className="flex items-center gap-3 py-3">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{row.label}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {row.who}
                      </p>
                    </div>
                    {row.state === "pending" ? (
                      <span className="rounded-full bg-primary/10 px-2.5 py-1 text-[0.7rem] font-medium text-primary">
                        Awaiting you
                      </span>
                    ) : row.state === "sandbox" ? (
                      <span className="flex items-center gap-1.5 rounded-full bg-secondary px-2.5 py-1 text-[0.7rem] font-medium text-muted-foreground">
                        <ServerIcon className="size-3" />
                        Sandboxed
                      </span>
                    ) : row.state === "approved" ? (
                      <span className="flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-1 text-[0.7rem] font-medium text-primary">
                        <CheckIcon className="size-3" />
                        Approved
                      </span>
                    ) : (
                      <span className="rounded-full bg-secondary px-2.5 py-1 text-[0.7rem] font-medium text-muted-foreground">
                        Auto
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── Final CTA ────────────────────────────────────────────────── */}
      <section className="px-4 py-24 sm:px-6">
        <Reveal className="mx-auto max-w-5xl">
          <div className="relative overflow-hidden rounded-[2rem] bg-primary px-6 py-16 text-center sm:px-16 sm:py-20">
            <NetworkBackdrop className="pointer-events-none absolute inset-0 h-full w-full text-white opacity-[0.14]" />
            <div className="relative mx-auto max-w-2xl">
              <h2 className="font-heading text-[clamp(2rem,3.5vw+0.5rem,3.25rem)] font-semibold leading-[1.08] tracking-[-0.03em] text-balance text-primary-foreground">
                Build your AI team today
              </h2>
              <p className="mx-auto mt-4 max-w-xl text-lg leading-relaxed text-pretty text-primary-foreground/80">
                Start free, self-host when you&apos;re ready, and keep humans in
                control the whole way.
              </p>
              <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
                <Button
                  asChild
                  variant="secondary"
                  className="h-12 bg-background px-6 text-[0.95rem] text-foreground hover:bg-background/90"
                >
                  <Link href="/signup">
                    Get started free
                    <ArrowRightIcon data-icon="inline-end" />
                  </Link>
                </Button>
                <Button
                  asChild
                  className="h-12 bg-primary-foreground/10 px-6 text-[0.95rem] text-primary-foreground ring-1 ring-inset ring-primary-foreground/25 hover:bg-primary-foreground/15"
                >
                  <Link href="/login">Log in</Link>
                </Button>
              </div>
            </div>
          </div>
        </Reveal>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────── */}
      <footer className="border-t border-border/60">
        <div className="mx-auto flex max-w-6xl flex-col gap-8 px-4 py-12 sm:px-6 md:flex-row md:items-center md:justify-between">
          <div className="max-w-xs">
            <div className="flex items-center gap-2.5">
              <SparklesIcon className="size-5 text-primary" />
              <span className="font-heading text-[0.9375rem] font-semibold tracking-tight">
                Deep-Foundry
              </span>
            </div>
            <p className="mt-3 text-sm text-muted-foreground text-pretty">
              Persistent AI coworkers with memory and human-controlled
              permissions. A DeepSeek product.
            </p>
          </div>
          <nav className="flex flex-wrap gap-x-8 gap-y-3 text-sm">
            <a
              href="#how-it-works"
              className="text-muted-foreground transition-colors hover:text-foreground"
            >
              How it works
            </a>
            <a
              href="#capabilities"
              className="text-muted-foreground transition-colors hover:text-foreground"
            >
              Capabilities
            </a>
            <a
              href="#control"
              className="text-muted-foreground transition-colors hover:text-foreground"
            >
              Control
            </a>
            <Link
              href="/login"
              className="text-muted-foreground transition-colors hover:text-foreground"
            >
              Log in
            </Link>
            <Link
              href="/signup"
              className="font-medium text-foreground transition-colors hover:text-primary"
            >
              Get started
            </Link>
          </nav>
        </div>
        <div className="border-t border-border/60">
          <p className="mx-auto max-w-6xl px-4 py-5 text-xs text-muted-foreground sm:px-6">
            © {new Date().getFullYear()} Deep-Foundry. Self-hostable and yours.
          </p>
        </div>
      </footer>
    </div>
  );
}
