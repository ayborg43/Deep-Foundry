"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { AuthShowcase } from "@/components/auth/auth-showcase";
import { GoogleAuthButton } from "@/components/google-auth-button";
import { LogoMark } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { setTokens } from "@/lib/auth";
import { cn } from "@/lib/utils";
import type { LoginResponse, Tokens } from "@/lib/types";

// Sized up from the compact app-shell defaults (h-8/h-9) — this is a
// once-per-session, front-door surface, not dense product chrome.
const fieldClass = "h-11 rounded-xl px-3.5 text-base";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleLoginSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const result = await apiFetch<LoginResponse>("/auth/login", {
        method: "POST",
        auth: false,
        body: JSON.stringify({ email, password }),
      });

      if ("mfa_required" in result && result.mfa_required) {
        setMfaToken(result.mfa_token);
        return;
      }

      setTokens(result.tokens);
      router.push("/home");
    } catch (err) {
      setError(
        err instanceof ApiRequestError
          ? err.message
          : "Something went wrong. Please try again."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleMfaSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!mfaToken) return;
    setError(null);
    setIsSubmitting(true);

    try {
      const result = await apiFetch<{ tokens: Tokens }>("/auth/mfa/verify", {
        method: "POST",
        auth: false,
        body: JSON.stringify({ mfa_token: mfaToken, code }),
      });
      setTokens(result.tokens);
      router.push("/home");
    } catch (err) {
      setError(
        err instanceof ApiRequestError
          ? err.message
          : "Something went wrong. Please try again."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <AuthShowcase />

      <div className="flex flex-col justify-center px-6 py-12 sm:px-10 md:px-16 lg:px-14 xl:px-20">
        <div className="auth-panel-in mx-auto w-full max-w-sm">
          <div className="mb-9 flex items-center justify-between">
            <Link
              href="/"
              aria-label="Back to Deep-Foundry home"
              className="flex items-center gap-2 opacity-90 transition-opacity hover:opacity-100"
            >
              <LogoMark />
              <span className="font-heading text-[0.9375rem] font-semibold tracking-tight">
                Deep-Foundry
              </span>
            </Link>
            <ThemeToggle variant="icon" />
          </div>

          {mfaToken ? (
            <>
              <h1 className="font-heading text-[1.75rem] font-medium tracking-[-0.02em] text-balance">
                Two-factor verification
              </h1>
              <p className="mt-1.5 text-[0.9375rem] text-muted-foreground">
                Enter the 6-digit code from your authenticator app.
              </p>

              <form onSubmit={handleMfaSubmit} className="mt-7 flex flex-col gap-4">
                {error ? (
                  <Alert variant="destructive">
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                ) : null}

                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="code">Authentication code</Label>
                  <Input
                    id="code"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={6}
                    required
                    autoFocus
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    className={cn(fieldClass, "text-center tracking-[0.3em]")}
                  />
                </div>

                <Button type="submit" className="h-11 w-full rounded-xl text-base" disabled={isSubmitting}>
                  {isSubmitting ? "Verifying…" : "Verify"}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  className="h-11 w-full rounded-xl text-base"
                  onClick={() => {
                    setMfaToken(null);
                    setCode("");
                    setError(null);
                  }}
                >
                  Back to login
                </Button>
              </form>
            </>
          ) : (
            <>
              <h1 className="font-heading text-[1.75rem] font-medium tracking-[-0.02em] text-balance">
                Welcome back
              </h1>
              <p className="mt-1.5 text-[0.9375rem] text-muted-foreground">
                Log in to your Deep-Foundry workspace.
              </p>

              <form onSubmit={handleLoginSubmit} className="mt-7 flex flex-col gap-4">
                {error ? (
                  <Alert variant="destructive">
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                ) : null}

                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    autoComplete="email"
                    required
                    autoFocus
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className={fieldClass}
                  />
                </div>

                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="password">Password</Label>
                  <Input
                    id="password"
                    type="password"
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className={fieldClass}
                  />
                </div>

                <Button
                  type="submit"
                  className="mt-1 h-11 w-full rounded-xl text-base"
                  disabled={isSubmitting}
                >
                  {isSubmitting ? "Logging in…" : "Log in"}
                </Button>

                <div className="relative py-1 text-center text-xs text-muted-foreground">
                  <span className="relative bg-background px-2">or</span>
                  <div className="absolute inset-x-0 top-1/2 -z-10 border-t" />
                </div>

                <GoogleAuthButton className="h-11 rounded-xl text-base" />
              </form>

              <p className="mt-8 text-center text-sm text-muted-foreground">
                Don&apos;t have an account?{" "}
                <Link
                  href="/signup"
                  className="font-medium text-foreground underline-offset-4 hover:underline"
                >
                  Sign up
                </Link>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
