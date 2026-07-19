"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { ArrowRightIcon, MailCheckIcon } from "lucide-react";

import { AuthShell } from "@/components/auth/auth-shell";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch, ApiRequestError } from "@/lib/api";

const fieldClass = "h-10 rounded-[9px] bg-card px-3 text-[0.875rem]";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      await apiFetch("/auth/password-reset/request", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      setSent(true);
    } catch (err) {
      setError(
        err instanceof ApiRequestError ? err.message : "Couldn't send the reset email. Try again."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthShell active="login">
      {sent ? (
        <>
          <div className="mb-4 flex size-11 items-center justify-center rounded-xl bg-primary/12 text-primary">
            <MailCheckIcon className="size-5" />
          </div>
          <h1 className="text-[1.375rem] font-bold tracking-[-0.02em]">Check your inbox</h1>
          <p className="mt-1 text-[0.8125rem] leading-5 text-muted-foreground">
            If an account exists for <span className="font-medium text-foreground">{email}</span>,
            a reset link is on its way. The link works once and expires after a while.
          </p>
          <Link
            href="/login"
            className="mt-6 text-[0.8125rem] font-medium text-primary hover:underline"
          >
            &larr; Back to sign in
          </Link>
        </>
      ) : (
        <>
          <h1 className="text-[1.375rem] font-bold tracking-[-0.02em]">Reset your password</h1>
          <p className="mt-1 text-[0.8125rem] leading-5 text-muted-foreground">
            Enter the email you signed up with and we&apos;ll send you a link to set a new
            password.
          </p>

          <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
            {error ? (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
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

            <Button
              type="submit"
              className="h-[42px] rounded-[9px] bg-foreground text-background hover:bg-foreground/90"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Sending…" : "Send reset link"}
              {!isSubmitting ? <ArrowRightIcon data-icon="inline-end" /> : null}
            </Button>

            <Link
              href="/login"
              className="text-center text-[0.8125rem] font-medium text-muted-foreground hover:text-foreground"
            >
              Back to sign in
            </Link>
          </form>
        </>
      )}
    </AuthShell>
  );
}
