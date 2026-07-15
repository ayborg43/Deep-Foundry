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
import { clearTokens, getTokens } from "@/lib/auth";
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

  // Delete-account danger zone.
  const [showDelete, setShowDelete] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

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

  const emailMatches =
    !!me && deleteConfirm.trim().toLowerCase() === me.email.trim().toLowerCase();

  async function handleDelete(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!emailMatches || isDeleting) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await apiFetch("/me", {
        method: "DELETE",
        body: JSON.stringify({ confirm_email: deleteConfirm.trim() }),
      });
      clearTokens();
      router.push("/signup");
    } catch (err) {
      setDeleteError(
        err instanceof ApiRequestError
          ? err.message
          : "Couldn't delete your account. Please try again."
      );
      setIsDeleting(false);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-lg flex-1 flex-col gap-6 px-4 py-12">
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

      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle className="text-xl text-destructive">Delete account</CardTitle>
          <CardDescription>
            Permanently delete your account, your personal workspace, and everything in it —
            coworkers, tasks, conversations, knowledge, and memory. This cannot be undone.
          </CardDescription>
        </CardHeader>

        <CardContent className="flex flex-col gap-4">
          {deleteError ? (
            <Alert variant="destructive">
              <AlertDescription>{deleteError}</AlertDescription>
            </Alert>
          ) : null}

          {!showDelete ? (
            <Button
              type="button"
              variant="destructive"
              className="w-fit"
              disabled={isLoading || !me}
              onClick={() => setShowDelete(true)}
            >
              Delete account
            </Button>
          ) : (
            <form onSubmit={handleDelete} className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="delete_confirm">
                  Type <span className="font-semibold text-foreground">{me?.email}</span> to confirm
                </Label>
                <Input
                  id="delete_confirm"
                  type="email"
                  autoComplete="off"
                  placeholder={me?.email}
                  value={deleteConfirm}
                  onChange={(e) => setDeleteConfirm(e.target.value)}
                  aria-invalid={deleteConfirm.length > 0 && !emailMatches}
                />
              </div>
              <div className="flex items-center gap-2">
                <Button
                  type="submit"
                  variant="destructive"
                  disabled={!emailMatches || isDeleting}
                >
                  {isDeleting ? "Deleting…" : "Permanently delete account"}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  disabled={isDeleting}
                  onClick={() => {
                    setShowDelete(false);
                    setDeleteConfirm("");
                    setDeleteError(null);
                  }}
                >
                  Cancel
                </Button>
              </div>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
