"use client";

import { QRCodeSVG } from "qrcode.react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch, ApiRequestError } from "@/lib/api";
import { getTokens } from "@/lib/auth";
import type { User } from "@/lib/types";

type EnrollResponse = { secret: string; otpauth_url: string };

export default function MfaSettingsPage() {
  const router = useRouter();
  const [me, setMe] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [enrollment, setEnrollment] = useState<EnrollResponse | null>(null);
  const [code, setCode] = useState("");
  const [isEnrolling, setIsEnrolling] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);

  useEffect(() => {
    if (!getTokens()) {
      router.push("/login");
      return;
    }

    apiFetch<User>("/me")
      .then(setMe)
      .catch((err) => {
        setError(
          err instanceof ApiRequestError
            ? err.message
            : "Couldn't load your account details."
        );
      })
      .finally(() => setIsLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleEnroll() {
    setIsEnrolling(true);
    setError(null);
    try {
      const result = await apiFetch<EnrollResponse>("/auth/mfa/enroll", {
        method: "POST",
      });
      setEnrollment(result);
    } catch (err) {
      setError(
        err instanceof ApiRequestError
          ? err.message
          : "Couldn't start MFA enrollment."
      );
    } finally {
      setIsEnrolling(false);
    }
  }

  async function handleConfirm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsConfirming(true);
    setError(null);

    try {
      await apiFetch<{ mfa_enabled: true }>("/auth/mfa/enroll/confirm", {
        method: "POST",
        body: JSON.stringify({ code }),
      });
      setConfirmed(true);
      setMe((prev) => (prev ? { ...prev, mfa_enabled: true } : prev));
    } catch (err) {
      setError(
        err instanceof ApiRequestError
          ? err.message
          : "That code didn't work. Check your authenticator app and try again."
      );
    } finally {
      setIsConfirming(false);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-lg flex-1 flex-col justify-center px-4 py-12">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Two-factor authentication</CardTitle>
          <CardDescription>
            Add an extra layer of security to your account using an
            authenticator app.
          </CardDescription>
        </CardHeader>

        <CardContent className="flex flex-col gap-4">
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading...</p>
          ) : confirmed || me?.mfa_enabled ? (
            <Alert>
              <AlertDescription>
                Two-factor authentication is enabled on your account.
              </AlertDescription>
            </Alert>
          ) : !enrollment ? (
            <>
              <p className="text-sm text-muted-foreground">
                MFA is not yet enabled. Start enrollment to get a QR code you
                can scan with an authenticator app (e.g. Google Authenticator,
                1Password, Authy).
              </p>
              <Button
                type="button"
                onClick={handleEnroll}
                disabled={isEnrolling}
                className="w-fit"
              >
                {isEnrolling ? "Starting..." : "Start enrollment"}
              </Button>
            </>
          ) : (
            <>
              <div className="flex flex-col items-center gap-3 rounded-lg border p-4">
                <QRCodeSVG value={enrollment.otpauth_url} size={180} />
                <p className="text-center text-xs text-muted-foreground">
                  Scan with your authenticator app, or enter this code
                  manually:
                </p>
                <code className="break-all rounded bg-muted px-2 py-1 text-center text-xs">
                  {enrollment.secret}
                </code>
              </div>

              <form onSubmit={handleConfirm} className="flex flex-col gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="mfa_code">6-digit code</Label>
                  <Input
                    id="mfa_code"
                    type="text"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={6}
                    required
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                  />
                </div>
                <Button type="submit" disabled={isConfirming} className="w-fit">
                  {isConfirming ? "Confirming..." : "Confirm and enable"}
                </Button>
              </form>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
