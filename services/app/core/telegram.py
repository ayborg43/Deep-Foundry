from __future__ import annotations

import html as _html
import json
import re
import urllib.error
import urllib.request
from urllib.parse import quote

from django.conf import settings

TELEGRAM_API_ORIGIN = "https://api.telegram.org"
_MAX_RESPONSE_BYTES = 64 * 1024
_BOT_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")

# Telegram caps a message at 4096 chars; leave headroom for safety and split
# long content on line boundaries so no formatting tag is severed mid-message.
_TELEGRAM_TEXT_LIMIT = 4096
_TELEGRAM_CHUNK_LIMIT = 3900

# Coworkers reply in Markdown, but Telegram sends plain text by default — so
# **bold**, `code`, and [text](url) leak as raw markers. These convert the small
# Markdown subset coworkers actually use into the HTML subset Telegram renders.
# All patterns are single-line (no DOTALL) so a tag never spans a newline, which
# keeps line-boundary chunking safe.
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_MD_BOLD_ALT_RE = re.compile(r"__(.+?)__")
_MD_CODE_RE = re.compile(r"`([^`]+)`")
_MD_HEADING_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s+(.*\S)\s*$")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def markdown_to_telegram_html(text: str) -> str:
    """Render the coworker's Markdown as Telegram HTML (bold, code, links) so a
    reply shows formatted instead of leaking raw ** and [] markers. Everything
    else is HTML-escaped first, so stray < > & can't break parsing."""
    escaped = _html.escape(text, quote=False)

    def _link(match: re.Match) -> str:
        return f'<a href="{_html.escape(match.group(2), quote=True)}">{match.group(1)}</a>'

    out = _MD_LINK_RE.sub(_link, escaped)
    out = _MD_HEADING_RE.sub(r"<b>\1</b>", out)
    out = _MD_BOLD_RE.sub(r"<b>\1</b>", out)
    out = _MD_BOLD_ALT_RE.sub(r"<b>\1</b>", out)
    out = _MD_CODE_RE.sub(r"<code>\1</code>", out)
    return out


def _html_to_plain(text: str) -> str:
    """Strip HTML tags and unescape entities — the plain-text fallback when
    Telegram can't parse a chunk as HTML."""
    return _html.unescape(_HTML_TAG_RE.sub("", text))


def _chunk_for_telegram(text: str, limit: int = _TELEGRAM_CHUNK_LIMIT) -> list[str]:
    """Split into <=limit pieces on line boundaries so a message never exceeds
    Telegram's cap and no inline tag is cut in half."""
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        while len(line) > limit:  # a single very long line — hard-split it
            chunks.append(line[:limit])
            line = line[limit:]
        current = line
    if current:
        chunks.append(current)
    return chunks or [""]


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


def send_telegram_message(chat_id: int, text: str, parse_mode: str | None = None) -> str:
    payload: dict = {
        "chat_id": chat_id,
        "text": text[:_TELEGRAM_TEXT_LIMIT],
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    result = _bot_api_request("sendMessage", payload)
    return str(result.get("result", {}).get("message_id", ""))


def send_telegram_rich(chat_id: int, markdown_text: str) -> str:
    """Deliver a coworker's Markdown reply formatted, split across as many
    messages as its length needs. Each chunk is sent as HTML; if Telegram can't
    parse a chunk (unbalanced tag from a hard split, say), that chunk is resent
    as plain text so delivery never fails over formatting. Returns the last
    message id."""
    chunks = _chunk_for_telegram(markdown_to_telegram_html(markdown_text))
    last_id = ""
    for chunk in chunks:
        try:
            last_id = send_telegram_message(chat_id, chunk, parse_mode="HTML")
        except TelegramPermanentError:
            last_id = send_telegram_message(chat_id, _html_to_plain(chunk))
    return last_id


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
