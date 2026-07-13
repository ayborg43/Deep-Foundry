"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { setTokens, setWorkspaceId } from "@/lib/auth";
import { getGoogleRedirectUri } from "@/lib/google-oauth";
import type { AuthSuccess } from "@/lib/types";

function GoogleCallbackInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // Derived directly from the URL at render time (no effect needed for
  // these two — only the async exchange below needs one).
  const code = searchParams.get("code");
  const oauthError = searchParams.get("error");
  const paramsError = oauthError
    ? `Google sign-in was cancelled or failed (${oauthError}).`
    : !code
      ? "Missing authorization code from Google."
      : null;

  const [exchangeError, setExchangeError] = useState<string | null>(null);

  useEffect(() => {
    if (paramsError || !code) {
      return;
    }

    apiFetch<AuthSuccess>("/auth/oauth/google/callback", {
      method: "POST",
      body: JSON.stringify({ code, redirect_uri: getGoogleRedirectUri() }),
    })
      .then((result) => {
        setTokens(result.tokens);
        setWorkspaceId(result.workspace.id);
        router.push("/");
      })
      .catch((err) => {
        setExchangeError(
          err instanceof ApiRequestError
            ? err.message
            : "Something went wrong finishing Google sign-in."
        );
      });
    // Only run once per code — router/paramsError are stable for a given code.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code]);

  const error = paramsError ?? exchangeError;

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-12">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-xl">Signing in with Google</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {error ? (
            <>
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
              <Button className="w-full" onClick={() => router.push("/login")}>
                Back to login
              </Button>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              Please wait while we finish signing you in...
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function GoogleCallbackPage() {
  return (
    <Suspense>
      <GoogleCallbackInner />
    </Suspense>
  );
}
