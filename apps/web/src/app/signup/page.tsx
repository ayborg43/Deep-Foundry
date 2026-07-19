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
import { setTokens, setWorkspaceId } from "@/lib/auth";
import { cn } from "@/lib/utils";
import type { AuthSuccess } from "@/lib/types";

const fieldClass = "h-10 rounded-[9px] bg-card px-3 text-[0.875rem]";

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setIsSubmitting(true);

    try {
      const result = await apiFetch<AuthSuccess>("/auth/register", {
        method: "POST",
        auth: false,
        body: JSON.stringify({
          email,
          password,
          ...(displayName ? { display_name: displayName } : {}),
        }),
      });
      setTokens(result.tokens);
      setWorkspaceId(result.workspace.id);
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
    setNotice(`${provider} sign-up is not configured on this Foundry instance.`);
  }

  return (
    <AuthShell active="signup">
      <h1 className="text-[1.375rem] font-bold tracking-[-0.02em]">Create your account</h1>
      <p className="mt-1 text-[0.8125rem] leading-5 text-muted-foreground">
        Set up your foundry and hire your first persistent coworker.
      </p>

      <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
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
          <Label htmlFor="display_name">Name</Label>
          <Input
            id="display_name"
            autoComplete="name"
            placeholder="Sarah Okonkwo"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            className={fieldClass}
          />
        </div>

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
          <Label htmlFor="password">Password</Label>
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              minLength={8}
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
          <p className="text-[0.6875rem] text-muted-foreground">
            Use at least 8 characters.
          </p>
        </div>

        <Button
          type="submit"
          className="h-[42px] rounded-[9px] bg-foreground text-background hover:bg-foreground/90"
          disabled={isSubmitting}
        >
          {isSubmitting ? "Creating account…" : "Create account"}
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
        Already have an account?{" "}
        <Link href="/login" className="font-semibold text-primary hover:underline">
          Sign in
        </Link>
      </p>
    </AuthShell>
  );
}
