import Link from "next/link";
import {
  ArrowRightIcon,
  UsersIcon,
  ListTodoIcon,
  ShieldCheckIcon,
  BrainIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";

const FEATURES = [
  {
    icon: UsersIcon,
    title: "Persistent coworkers",
    body: "AI teammates with their own role, model, and tools — always on, always yours.",
  },
  {
    icon: ListTodoIcon,
    title: "Background tasks",
    body: "Hand off work and walk away. It runs on its own and returns a finished result.",
  },
  {
    icon: ShieldCheckIcon,
    title: "Approval gates",
    body: "Nothing risky happens without your sign-off. You stay in control of every step.",
  },
  {
    icon: BrainIcon,
    title: "Memory & knowledge",
    body: "Coworkers remember context and draw on a knowledge base that grows with you.",
  },
];

export default function Home() {
  return (
    <div className="flex flex-1 flex-col">
      {/* Hero */}
      <section className="mx-auto flex w-full max-w-3xl flex-col items-center px-4 pt-20 pb-16 text-center sm:pt-28">
        <span className="mb-6 inline-flex items-center gap-2 rounded-full border border-border/70 bg-card/60 px-3 py-1 text-xs font-medium text-muted-foreground backdrop-blur-sm">
          <span aria-hidden className="text-primary">✳</span>
          Persistent AI coworkers for your team
        </span>

        <h1 className="font-heading text-4xl font-semibold tracking-tight text-balance sm:text-6xl">
          Your AI team, working
          <span className="text-primary"> while you don&apos;t</span>.
        </h1>

        <p className="mt-6 max-w-xl text-base text-muted-foreground text-pretty sm:text-lg">
          Deep-Foundry gives you AI coworkers with memory, tools, and
          human-controlled permissions. Assign a task, approve what matters, and
          come back to finished work.
        </p>

        <div className="mt-9 flex flex-col items-center gap-3 sm:flex-row">
          <Button asChild size="lg" className="h-11 px-5 text-sm">
            <Link href="/signup">
              Get started free
              <ArrowRightIcon data-icon="inline-end" />
            </Link>
          </Button>
          <Button asChild size="lg" variant="outline" className="h-11 px-5 text-sm">
            <Link href="/login">Log in</Link>
          </Button>
        </div>

        <p className="mt-4 text-xs text-muted-foreground">
          No credit card required · Free to start
        </p>
      </section>

      {/* Feature grid */}
      <section className="mx-auto w-full max-w-5xl px-4 pb-24">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {FEATURES.map((feature) => {
            const Icon = feature.icon;
            return (
              <div
                key={feature.title}
                className="flex gap-4 rounded-2xl border border-border/70 bg-card/60 p-5 backdrop-blur-sm transition-colors hover:border-primary/40"
              >
                <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/12 text-primary">
                  <Icon className="size-5" />
                </span>
                <div className="flex flex-col gap-1">
                  <h2 className="font-heading text-base font-semibold tracking-tight">
                    {feature.title}
                  </h2>
                  <p className="text-sm text-muted-foreground text-pretty">
                    {feature.body}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
