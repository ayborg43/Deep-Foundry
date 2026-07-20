"""Client for the separately isolated JavaScript browser service."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings

from ai.web_reader import WebPageError, validate_public_url


class BrowserReadError(RuntimeError):
    pass


def browse_webpage(
    url: str,
    *,
    blocked_domains: list[str] | None = None,
) -> dict[str, Any]:
    if not settings.BROWSER_SERVICE_URL or not settings.BROWSER_SERVICE_TOKEN:
        raise BrowserReadError("The isolated browser service is not configured.")
    try:
        normalized = validate_public_url(url)
    except WebPageError as exc:
        raise BrowserReadError(str(exc)) from exc
    payload = json.dumps(
        {
            "url": normalized,
            "blocked_domains": [str(item) for item in (blocked_domains or [])[:100]],
        }
    ).encode()
    request = urllib.request.Request(
        f"{settings.BROWSER_SERVICE_URL.rstrip('/')}/browse",
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.BROWSER_SERVICE_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=settings.BROWSER_SERVICE_TIMEOUT_SECONDS,
        ) as response:
            body = response.read(settings.BROWSER_SERVICE_MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        detail = exc.read(4000).decode(errors="replace")
        try:
            message = json.loads(detail).get("error", detail)
        except json.JSONDecodeError:
            message = detail
        raise BrowserReadError(f"The browser could not render the page: {message}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise BrowserReadError(f"The isolated browser service is unavailable: {exc}") from exc
    if len(body) > settings.BROWSER_SERVICE_MAX_RESPONSE_BYTES:
        raise BrowserReadError("The browser response exceeded the configured limit.")
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise BrowserReadError("The browser service returned invalid JSON.") from exc
    final_url = result.get("url")
    try:
        validate_public_url(final_url)
    except WebPageError as exc:
        raise BrowserReadError("The browser returned an unsafe final URL.") from exc
    return result
