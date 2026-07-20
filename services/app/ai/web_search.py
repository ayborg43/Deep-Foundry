"""Small, bounded web and news search used by the built-in ``web_search`` tool.

The default provider is DuckDuckGo's HTML endpoint, which keeps self-hosting
usable without requiring a second paid API key. Operators may point the
endpoint at a compatible mirror through ``WEB_SEARCH_ENDPOINT``.
"""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from django.conf import settings

from .news_search import NewsSearchError, search_news


class WebSearchError(RuntimeError):
    pass


class _ResultsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._anchor: dict[str, str] | None = None
        self._in_snippet = False
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if tag == "a" and "result__a" in classes:
            self._anchor = {"title": "", "url": values.get("href") or "", "snippet": ""}
            self._text = []
        elif "result__snippet" in classes and self.results:
            self._in_snippet = True
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._anchor is not None or self._in_snippet:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor is not None:
            self._anchor["title"] = " ".join("".join(self._text).split())
            self._anchor["url"] = _unwrap_url(self._anchor["url"])
            if self._anchor["title"] and self._anchor["url"]:
                self.results.append(self._anchor)
            self._anchor = None
            self._text = []
        elif self._in_snippet and tag in {"a", "div", "span"}:
            self.results[-1]["snippet"] = " ".join("".join(self._text).split())
            self._in_snippet = False
            self._text = []


def _unwrap_url(url: str) -> str:
    parsed = urlparse(url)
    redirected = parse_qs(parsed.query).get("uddg")
    return redirected[0] if redirected else url


def _search_duckduckgo(query: str, *, limit: int) -> list[dict[str, str]]:
    request = Request(
        settings.WEB_SEARCH_ENDPOINT,
        data=urlencode({"q": query}).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Deep-Foundry/1.0 (self-hosted web search)",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.WEB_SEARCH_TIMEOUT_SECONDS) as response:
            body = response.read(settings.WEB_SEARCH_MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise WebSearchError(f"Web search provider request failed: {exc}") from exc
    if len(body) > settings.WEB_SEARCH_MAX_RESPONSE_BYTES:
        raise WebSearchError("Web search provider response exceeded the configured limit.")

    parser = _ResultsParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    for result in parser.results:
        result["provider"] = "duckduckgo"
    return parser.results[:limit]


def _merge_results(
    web_results: list[dict[str, str]],
    news_results: list[dict[str, str]],
    *,
    limit: int,
) -> list[dict[str, str]]:
    combined: list[dict[str, str]] = []
    seen: set[str] = set()
    for index in range(max(len(web_results), len(news_results))):
        for collection in (web_results, news_results):
            if index >= len(collection):
                continue
            result = collection[index]
            url = str(result.get("url", "")).strip()
            key = url.rstrip("/").casefold()
            if not url or key in seen:
                continue
            seen.add(key)
            combined.append(result)
            if len(combined) == limit:
                return combined
    return combined


def search_web(query: str, *, max_results: int | None = None) -> list[dict[str, str]]:
    query = query.strip()
    if not query:
        raise WebSearchError("web_search requires a non-empty query.")
    if len(query) > 500:
        raise WebSearchError("web_search queries are limited to 500 characters.")

    limit = min(max_results or settings.WEB_SEARCH_MAX_RESULTS, 10)
    web_results: list[dict[str, str]] = []
    news_results: list[dict[str, str]] = []
    web_error: WebSearchError | None = None
    try:
        web_results = _search_duckduckgo(query, limit=limit)
    except WebSearchError as exc:
        web_error = exc
    if settings.NEWS_SEARCH_ENABLED:
        try:
            news_results = search_news(query, max_results=limit)
        except NewsSearchError:
            pass
    if not web_results and not news_results and web_error is not None:
        raise web_error
    return _merge_results(web_results, news_results, limit=limit)
