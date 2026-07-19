"use client";

import Link from "next/link";

import { AuthShowcase } from "@/components/auth/auth-showcase";
import { LogoMark } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";

export function AuthShell({
  active,
  children,
}: {
  active: "login" | "signup";
  children: React.ReactNode;
}) {
  return (
    <div className="grid min-h-svh bg-background lg:grid-cols-[51.25%_48.75%]">
      <AuthShowcase />

      <section className="relative flex min-h-svh flex-col px-5 py-5 sm:px-8 lg:px-12">
        <ThemeToggle
          variant="icon"
          className="absolute right-5 top-5 rounded-[10px] border border-border bg-card shadow-[var(--shadow-sm)] sm:right-6"
        />

        <Link
          href="/"
          aria-label="Back to Deep-Foundry home"
          className="flex w-fit items-center gap-2.5 pr-14 lg:hidden"
        >
          <LogoMark className="size-9" />
          <span className="leading-tight">
            <span className="block text-sm font-bold">Deep-Foundry</span>
            <span className="block text-[0.6875rem] text-muted-foreground">
              AI operating system for coworkers
            </span>
          </span>
        </Link>

        <div className="auth-panel-in mx-auto flex w-full max-w-[392px] flex-1 flex-col justify-center py-16 lg:py-24">
          <nav
            aria-label="Authentication"
            className="mb-7 grid grid-cols-2 rounded-xl border border-border bg-muted p-[3px]"
          >
            <Link
              href="/login"
              aria-current={active === "login" ? "page" : undefined}
              className={`flex min-h-9 items-center justify-center rounded-[9px] text-[0.8125rem] font-semibold transition-[background-color,color,box-shadow] ${
                active === "login"
                  ? "bg-card text-foreground shadow-[var(--shadow-sm)]"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Sign in
            </Link>
            <Link
              href="/signup"
              aria-current={active === "signup" ? "page" : undefined}
              className={`flex min-h-9 items-center justify-center rounded-[9px] text-[0.8125rem] font-semibold transition-[background-color,color,box-shadow] ${
                active === "signup"
                  ? "bg-card text-foreground shadow-[var(--shadow-sm)]"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Create account
            </Link>
          </nav>

          {children}
        </div>

        <footer className="flex flex-wrap items-center justify-center gap-x-1 pb-1 text-[0.6875rem] text-muted-foreground">
          <span>Deep-Foundry is open-source.</span>
          <Link href="/#docs" className="font-semibold text-primary hover:underline">
            Read the docs
          </Link>
          <span>·</span>
          <Link href="/#self-host" className="font-semibold text-primary hover:underline">
            Self-host guide
          </Link>
        </footer>
      </section>
    </div>
  );
}
