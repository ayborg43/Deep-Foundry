"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { GoogleAuthButton } from "@/components/google-auth-button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { setTokens, setWorkspaceId } from "@/lib/auth";
import type { AuthSuccess } from "@/lib/types";

export default function SignupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
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
          : "Something went wrong. Please try again."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 px-4 py-12">
      <Link href="/" className="flex flex-col items-center gap-1.5 text-center">
        <span aria-hidden className="text-3xl leading-none text-primary">✳</span>
        <span className="font-heading text-xl font-semibold tracking-tight">Deep-Foundry</span>
      </Link>
      <Card className="w-full max-w-sm shadow-xl shadow-foreground/5">
        <CardHeader>
          <CardTitle className="text-xl">Create your account</CardTitle>
          <CardDescription>
            Set up your Deep-Foundry workspace to get started.
          </CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="flex flex-col gap-4">
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
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="display_name">Display name (optional)</Label>
              <Input
                id="display_name"
                type="text"
                autoComplete="name"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? "Creating account..." : "Create account"}
            </Button>

            <div className="relative py-1 text-center text-xs text-muted-foreground">
              <span className="relative bg-card px-2">or</span>
              <div className="absolute inset-x-0 top-1/2 -z-10 border-t" />
            </div>

            <GoogleAuthButton />
          </CardContent>
        </form>
        <CardFooter className="justify-center text-sm text-muted-foreground">
          Already have an account?
          <Link href="/login" className="ml-1 font-medium text-foreground underline-offset-4 hover:underline">
            Log in
          </Link>
        </CardFooter>
      </Card>
    </div>
  );
}
