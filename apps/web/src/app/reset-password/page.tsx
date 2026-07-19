"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { ArrowRightIcon, EyeIcon, EyeOffIcon } from "lucide-react";

import { AuthShell } from "@/components/auth/auth-shell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { cn } from "@/lib/utils";

const fieldClass = "h-10 rounded-[9px] bg-card px-3 text-[0.875rem]";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const uid = searchParams.get("uid") ?? "";
  const token = searchParams.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!uid || !token) {
    return (
      <>
        <h1 className="text-[1.375rem] font-bold tracking-[-0.02em]">Invalid reset link</h1>
        <p className="mt-1 text-[0.8125rem] leading-5 text-muted-foreground">
          This link is missing its reset token — it may have been truncated by your email
          client. Request a fresh one and try again.
        </p>
        <Link
          href="/forgot-password"
          className="mt-6 text-[0.8125rem] font-medium text-primary hover:underline"
        >
          Request a new link &rarr;
        </Link>
      </>
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("The two passwords don't match.");
      return;
    }
    setIsSubmitting(true);
    try {
      await apiFetch("/auth/password-reset/confirm", {
        method: "POST",
        body: JSON.stringify({ uid, token, password }),
      });
      router.push("/login");
    } catch (err) {
      setError(
        err instanceof ApiRequestError
          ? err.message
          : "Couldn't reset the password. The link may have expired — request a new one."
      );
      setIsSubmitting(false);
    }
  }

  return (
    <>
      <h1 className="text-[1.375rem] font-bold tracking-[-0.02em]">Choose a new password</h1>
      <p className="mt-1 text-[0.8125rem] leading-5 text-muted-foreground">
        Set a new password for your account. You&apos;ll sign in with it right after.
      </p>

      <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        <div className="grid gap-1.5">
          <Label htmlFor="password">New password</Label>
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              required
              autoFocus
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

        <div className="grid gap-1.5">
          <Label htmlFor="confirm">Confirm new password</Label>
          <Input
            id="confirm"
            type={showPassword ? "text" : "password"}
            autoComplete="new-password"
            required
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
            className={fieldClass}
          />
        </div>

        <Button
          type="submit"
          className="h-[42px] rounded-[9px] bg-foreground text-background hover:bg-foreground/90"
          disabled={isSubmitting}
        >
          {isSubmitting ? "Saving…" : "Set new password"}
          {!isSubmitting ? <ArrowRightIcon data-icon="inline-end" /> : null}
        </Button>
      </form>
    </>
  );
}

export default function ResetPasswordPage() {
  return (
    <AuthShell active="login">
      <Suspense fallback={null}>
        <ResetPasswordForm />
      </Suspense>
    </AuthShell>
  );
}
