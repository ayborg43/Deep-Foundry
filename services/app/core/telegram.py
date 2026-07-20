from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from urllib.parse import quote

from django.conf import settings

TELEGRAM_API_ORIGIN = "https://api.telegram.org"
_MAX_RESPONSE_BYTES = 64 * 1024
_BOT_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")


class TelegramError(Exception):
    code = "telegram_error"


class TelegramNotConfiguredError(TelegramError):
    code = "not_configured"


class TelegramPermanentError(TelegramError):
    code = "permanent_error"


class TelegramRetryableError(TelegramError):
    def __init__(self, code: str = "temporary_error", retry_after: int | None = None):
        super().__init__(code)
        self.code = code
        self.retry_after = retry_after


def telegram_is_configured() -> bool:
    return bool(getattr(settings, "TELEGRAM_ENABLED", False))


def normalized_bot_username() -> str:
    username = str(getattr(settings, "TELEGRAM_BOT_USERNAME", "")).lstrip("@")
    if not _BOT_USERNAME_RE.fullmatch(username):
        raise TelegramNotConfiguredError("Telegram bot username is not configured.")
    return username


def telegram_deep_link(token: str) -> str:
    return f"https://t.me/{normalized_bot_username()}?start={quote(token, safe='')}"


def _bounded_retry_after(value) -> int:
    try:
        return min(max(int(value or 0), 1), 300)
    except (TypeError, ValueError):
        return 1


def _bot_api_request(method: str, payload: dict) -> dict:
    if not telegram_is_configured():
        raise TelegramNotConfiguredError("Telegram notifications are not configured.")
    token = settings.TELEGRAM_BOT_TOKEN
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        f"{TELEGRAM_API_ORIGIN}/bot{token}/{method}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=settings.TELEGRAM_API_TIMEOUT_SECONDS
        ) as response:
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raw = exc.read(_MAX_RESPONSE_BYTES)
        details: dict = {}
        try:
            details = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        if exc.code in (400, 403):
            raise TelegramPermanentError("Telegram rejected the destination.") from exc
        retry_after = details.get("parameters", {}).get("retry_after")
        raise TelegramRetryableError(
            code="rate_limited" if exc.code == 429 else "http_error",
            retry_after=_bounded_retry_after(retry_after) if exc.code == 429 else None,
        ) from exc
    except (TimeoutError, urllib.error.URLError, OSError) as exc:
        raise TelegramRetryableError(code="network_error") from exc

    if len(raw) > _MAX_RESPONSE_BYTES:
        raise TelegramRetryableError(code="response_too_large")
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TelegramRetryableError(code="invalid_response") from exc
    if result.get("ok") is not True:
        error_code = int(result.get("error_code") or 0)
        if error_code in (400, 403):
            raise TelegramPermanentError("Telegram rejected the destination.")
        retry_after = result.get("parameters", {}).get("retry_after")
        raise TelegramRetryableError(
            code="rate_limited" if error_code == 429 else "api_error",
            retry_after=_bounded_retry_after(retry_after) if error_code == 429 else None,
        )
    return result


def send_telegram_message(chat_id: int, text: str) -> str:
    result = _bot_api_request(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text[:4096],
            "disable_web_page_preview": True,
        },
    )
    return str(result.get("result", {}).get("message_id", ""))


def configure_telegram_webhook(webhook_url: str) -> None:
    _bot_api_request(
        "setWebhook",
        {
            "url": webhook_url,
            "secret_token": settings.TELEGRAM_WEBHOOK_SECRET,
            "allowed_updates": ["message"],
            "drop_pending_updates": False,
        },
    )
