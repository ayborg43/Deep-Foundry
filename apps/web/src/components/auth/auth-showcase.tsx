import Link from "next/link";
import { BrainCircuitIcon, LockKeyholeIcon, ShieldCheckIcon } from "lucide-react";

import { LogoMark } from "@/components/logo";

const FEATURES = [
  {
    icon: ShieldCheckIcon,
    label: "Nothing dangerous runs without your explicit approval.",
    accent: true,
  },
  {
    icon: LockKeyholeIcon,
    label: "Open-source and self-hosted — your data never leaves your instance.",
  },
  {
    icon: BrainCircuitIcon,
    label: "Every teammate keeps a dossier: identity, tools, and long-term memory.",
  },
];

export function AuthShowcase() {
  return (
    <aside
      className="relative hidden overflow-hidden border-r border-border bg-card lg:flex lg:min-h-svh lg:flex-col lg:justify-between"
      style={{
        backgroundImage:
          "linear-gradient(to right, color-mix(in oklab, var(--border) 34%, transparent) 1px, transparent 1px), linear-gradient(to bottom, color-mix(in oklab, var(--border) 34%, transparent) 1px, transparent 1px)",
        backgroundSize: "32px 32px",
      }}
    >
      <Link
        href="/"
        aria-label="Deep-Foundry home"
        className="relative m-10 flex w-fit items-center gap-3 xl:ml-12"
      >
        <LogoMark className="size-10" />
        <span className="leading-tight">
          <span className="block text-base font-bold tracking-[-0.01em]">Deep-Foundry</span>
          <span className="block text-xs text-muted-foreground">
            AI operating system for coworkers
          </span>
        </span>
      </Link>

      <div className="relative max-w-[490px] px-10 pb-16 xl:px-12">
        <h1 className="text-balance font-heading text-[clamp(2rem,2.4vw,2.45rem)] font-bold leading-[1.12] tracking-[-0.03em]">
          Your coworkers are
          <br />
          right where you left them.
        </h1>
        <p className="mt-5 max-w-[440px] text-[0.9375rem] leading-[1.65] text-muted-foreground">
          Sign in to the workshop. Persistent AI teammates keep their memory, their schedules,
          and their pending approvals — waiting for you, not reset to zero.
        </p>
        <ul className="mt-7 flex flex-col gap-3">
          {FEATURES.map(({ icon: Icon, label, accent }) => (
            <li
              key={label}
              className="flex max-w-[430px] items-start gap-2.5 text-[0.8125rem] leading-[1.45] text-muted-foreground"
            >
              <span
                className={`flex size-6 shrink-0 items-center justify-center rounded-lg border bg-card ${
                  accent ? "text-[#4e9a6a]" : "text-muted-foreground"
                }`}
              >
                <Icon aria-hidden="true" className="size-3.5" />
              </span>
              {label}
            </li>
          ))}
        </ul>
      </div>

      <div className="relative flex items-center justify-between px-10 pb-9 text-[0.6875rem] text-muted-foreground xl:px-12">
        <span className="inline-flex items-center gap-2">
          <span className="size-1.5 rounded-full bg-[#4e9a6a]" />
          foundry.northwind.internal
        </span>
        <span className="font-mono">v3.2.1 · MIT</span>
      </div>
    </aside>
  );
}
