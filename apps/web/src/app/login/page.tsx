"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import {
  ArrowRightIcon,
  EyeIcon,
  EyeOffIcon,
  LockKeyholeIcon,
} from "lucide-react";

import { GithubMark } from "@/components/auth/github-mark";
import { AuthShell } from "@/components/auth/auth-shell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { setTokens } from "@/lib/auth";
import { cn } from "@/lib/utils";
import type { LoginResponse, Tokens } from "@/lib/types";

const fieldClass = "h-10 rounded-[9px] bg-card px-3 text-[0.875rem]";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(true);
  const [code, setCode] = useState("");
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleLoginSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
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
          : "Something went wrong. Please try again.",
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
          : "Something went wrong. Please try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  function unavailable(provider: string) {
    setError(null);
    setNotice(`${provider} sign-in is not configured on this Foundry instance.`);
  }

  return (
    <AuthShell active="login">
      {mfaToken ? (
        <>
          <h1 className="text-[1.375rem] font-bold tracking-[-0.02em]">
            Two-factor verification
          </h1>
          <p className="mt-1 text-[0.8125rem] leading-5 text-muted-foreground">
            Enter the 6-digit code from your authenticator app.
          </p>

          <form onSubmit={handleMfaSubmit} className="mt-6 flex flex-col gap-4">
            {error ? (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            ) : null}
            <div className="grid gap-1.5">
              <Label htmlFor="code">Authentication code</Label>
              <Input
                id="code"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                required
                autoFocus
                value={code}
                onChange={(event) => setCode(event.target.value)}
                className={cn(fieldClass, "text-center font-mono tracking-[0.3em]")}
              />
            </div>
            <Button
              type="submit"
              className="h-[42px] rounded-[9px] bg-foreground text-background hover:bg-foreground/90"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Verifying…" : "Verify"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="h-10"
              onClick={() => {
                setMfaToken(null);
                setCode("");
                setError(null);
              }}
            >
              Back to sign in
            </Button>
          </form>
        </>
      ) : (
        <>
          <h1 className="text-[1.375rem] font-bold tracking-[-0.02em]">Welcome back</h1>
          <p className="mt-1 text-[0.8125rem] leading-5 text-muted-foreground">
            Sign in to your foundry to pick up where your coworkers left off.
          </p>

          <form onSubmit={handleLoginSubmit} className="mt-6 flex flex-col gap-4">
            {error ? (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            ) : null}
            {notice ? (
              <Alert>
                <AlertDescription>{notice}</AlertDescription>
              </Alert>
            ) : null}

            <div className="grid gap-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                autoFocus
                placeholder="sarah@northwind.co"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className={fieldClass}
              />
            </div>

            <div className="grid gap-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="password">Password</Label>
                <Link
                  href="/forgot-password"
                  className="text-xs font-medium text-primary hover:underline"
                >
                  Forgot?
                </Link>
              </div>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className={cn(fieldClass, "pr-10")}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((value) => !value)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-muted-foreground hover:text-foreground"
                >
                  {showPassword ? <EyeOffIcon className="size-4" /> : <EyeIcon className="size-4" />}
                </button>
              </div>
            </div>

            <label className="flex min-h-5 w-fit cursor-pointer items-center gap-2 text-[0.8125rem] text-muted-foreground">
              <input
                type="checkbox"
                checked={remember}
                onChange={(event) => setRemember(event.target.checked)}
                className="size-4 rounded accent-foreground"
              />
              Keep me signed in on this device
            </label>

            <Button
              type="submit"
              className="h-[42px] rounded-[9px] bg-foreground text-background hover:bg-foreground/90"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Signing in…" : "Sign in"}
              {!isSubmitting ? <ArrowRightIcon data-icon="inline-end" /> : null}
            </Button>

            <div className="flex items-center gap-3 text-[0.6875rem] text-muted-foreground">
              <span className="h-px flex-1 bg-border" />
              or continue with
              <span className="h-px flex-1 bg-border" />
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <Button
                type="button"
                variant="outline"
                className="h-10 rounded-[9px] bg-card"
                onClick={() => unavailable("GitHub")}
              >
                <GithubMark className="size-4" />
                GitHub
              </Button>
              <Button
                type="button"
                variant="outline"
                className="h-10 rounded-[9px] bg-card"
                onClick={() => unavailable("SSO / SAML")}
              >
                <LockKeyholeIcon />
                SSO / SAML
              </Button>
            </div>
          </form>

          <p className="mt-7 text-center text-[0.75rem] text-muted-foreground">
            New to this foundry?{" "}
            <Link href="/signup" className="font-semibold text-primary hover:underline">
              Create an account
            </Link>
          </p>
        </>
      )}
    </AuthShell>
  );
}
