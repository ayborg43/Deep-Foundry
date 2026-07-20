"""Keyless, bounded news discovery through GDELT's DOC 2 API."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache


class NewsSearchError(RuntimeError):
    pass


_LANGUAGE_CODES = {
    "arabic": "ar",
    "chinese": "zh",
    "english": "en",
    "french": "fr",
    "german": "de",
    "hindi": "hi",
    "italian": "it",
    "japanese": "ja",
    "portuguese": "pt",
    "russian": "ru",
    "spanish": "es",
}


def _published_at(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    for pattern in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S"):
        try:
            parsed = datetime.strptime(raw, pattern).replace(tzinfo=timezone.utc)
            return parsed.isoformat().replace("+00:00", "Z")
        except ValueError:
            continue
    return raw


def _normalize_article(article: object) -> dict[str, str] | None:
    if not isinstance(article, dict):
        return None
    url = str(article.get("url") or "").strip()
    title = " ".join(str(article.get("title") or "").split())
    if not url.startswith(("https://", "http://")) or not title:
        return None
    publisher = str(article.get("domain") or "").strip()
    raw_language = str(article.get("language") or "").strip()
    language = _LANGUAGE_CODES.get(raw_language.casefold(), raw_language)
    country = str(article.get("sourcecountry") or "").strip()
    details = [value for value in (publisher, country, language) if value]
    return {
        "url": url,
        "title": title,
        "snippet": " | ".join(details),
        "publisher": publisher,
        "published_at": _published_at(article.get("seendate")),
        "language": language,
        "country": country,
        "image_url": str(article.get("socialimage") or "").strip(),
        "provider": "gdelt",
    }


def search_news(
    query: str,
    *,
    max_results: int | None = None,
) -> list[dict[str, str]]:
    """Return recent news articles, using cache and a shared request slot.

    GDELT asks high-traffic clients to make no more than one request every five
    seconds. The cache-backed slot enforces that across web and worker processes;
    a busy slot simply lets the normal web-search fallback serve the request.
    """

    query = query.strip()
    if not query:
        raise NewsSearchError("News search requires a non-empty query.")
    if len(query) > 500:
        raise NewsSearchError("News search queries are limited to 500 characters.")

    limit = min(max_results or settings.NEWS_SEARCH_MAX_RESULTS, 10)
    cache_key = "news-search:gdelt:" + hashlib.sha256(
        f"{query.casefold()}:{limit}:{settings.NEWS_SEARCH_TIMESPAN}".encode()
    ).hexdigest()
    cached = cache.get(cache_key)
    if isinstance(cached, list):
        return cached[:limit]

    interval = max(float(settings.NEWS_SEARCH_MIN_INTERVAL_SECONDS), 5.0)
    if not cache.add(
        "news-search:gdelt:request-slot",
        "1",
        timeout=max(math.ceil(interval), 5),
    ):
        raise NewsSearchError("News provider request is rate limited; using web results.")

    params = {
        "query": query,
        "mode": "ArtList",
        "maxrecords": limit,
        "format": "json",
        "sort": "DateDesc",
        "timespan": settings.NEWS_SEARCH_TIMESPAN,
    }
    request = Request(
        f"{settings.NEWS_SEARCH_ENDPOINT}?{urlencode(params)}",
        headers={"User-Agent": "Deep-Foundry/1.0 (self-hosted news search)"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=settings.NEWS_SEARCH_TIMEOUT_SECONDS) as response:
            body = response.read(settings.NEWS_SEARCH_MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise NewsSearchError(f"News provider request failed: {exc}") from exc
    if len(body) > settings.NEWS_SEARCH_MAX_RESPONSE_BYTES:
        raise NewsSearchError("News provider response exceeded the configured limit.")

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NewsSearchError("News provider returned an invalid response.") from exc
    articles = payload.get("articles", []) if isinstance(payload, dict) else []
    results = [result for item in articles if (result := _normalize_article(item))]
    results = results[:limit]
    cache.set(cache_key, results, timeout=settings.NEWS_SEARCH_CACHE_SECONDS)
    return results
