// Builds the Google OAuth 2.0 authorization URL for the "Continue with
// Google" button. Returns null when no client id is configured so callers
// can hide/disable the button instead of erroring — there are no real
// Google credentials in this environment (Milestone 1 build-only scope).

export const GOOGLE_OAUTH_CALLBACK_PATH = "/auth/google/callback";

export function getGoogleOAuthUrl(): string | null {
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
  if (!clientId) {
    return null;
  }

  const redirectUri = `${window.location.origin}${GOOGLE_OAUTH_CALLBACK_PATH}`;
  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    response_type: "code",
    scope: "openid email profile",
  });

  return `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
}

export function getGoogleRedirectUri(): string {
  return `${window.location.origin}${GOOGLE_OAUTH_CALLBACK_PATH}`;
}
