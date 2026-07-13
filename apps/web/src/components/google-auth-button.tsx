"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { getGoogleOAuthUrl } from "@/lib/google-oauth";

export function GoogleAuthButton() {
  // Computed on mount only (needs window.location) — null until then, and
  // stays null forever if NEXT_PUBLIC_GOOGLE_CLIENT_ID isn't set, in which
  // case the button hides itself rather than erroring.
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    // Reads window.location, so it can only run post-mount — server and
    // first client render both intentionally show nothing (see comment
    // above), so this synchronous update doesn't cascade further renders.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setUrl(getGoogleOAuthUrl());
  }, []);

  if (!url) {
    return null;
  }

  return (
    <Button asChild type="button" variant="outline" className="w-full">
      <a href={url}>Continue with Google</a>
    </Button>
  );
}
