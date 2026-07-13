"""
Google OAuth2 authorization-code exchange + identity fetch.

Uses stdlib `urllib` rather than adding `requests`/`httpx` as a dependency —
this is two small POST/GET calls to fixed Google endpoints, not enough
surface to justify a new HTTP client library. Network calls are isolated in
this module specifically so tests can monkeypatch `exchange_code_for_tokens`
and `fetch_userinfo` without touching real HTTP.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"


class GoogleOAuthError(Exception):
    pass


def exchange_code_for_tokens(code: str, redirect_uri: str) -> dict:
    data = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode()
    request = urllib.request.Request(TOKEN_ENDPOINT, data=data, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise GoogleOAuthError(f"Google token exchange failed: {exc.read()}") from exc


def fetch_userinfo(access_token: str) -> dict:
    request = urllib.request.Request(
        USERINFO_ENDPOINT, headers={"Authorization": f"Bearer {access_token}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise GoogleOAuthError(f"Google userinfo fetch failed: {exc.read()}") from exc
