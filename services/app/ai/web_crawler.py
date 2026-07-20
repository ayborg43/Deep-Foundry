"""Responsible, bounded crawling for public research sources."""

from __future__ import annotations

import hashlib
import time
import urllib.robotparser
from collections import deque
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from defusedxml import ElementTree
from django.conf import settings
from django.core.cache import cache

from ai.web_reader import WebPageError, fetch_public_resource, read_webpage


class CrawlError(RuntimeError):
    pass


@dataclass(frozen=True)
class RobotsPolicy:
    parser: urllib.robotparser.RobotFileParser | None
    allow_all: bool
    sitemaps: tuple[str, ...]
    status_code: int | None

    def allowed(self, url: str) -> bool:
        if self.allow_all:
            return True
        if self.parser is None:
            return False
        return self.parser.can_fetch(settings.WEB_READER_USER_AGENT, url)


def normalize_domain(value: str) -> str:
    candidate = str(value or "").strip().lower().rstrip(".")
    if "://" in candidate:
        candidate = urlsplit(candidate).hostname or ""
    try:
        return candidate.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise CrawlError(f"Invalid domain {value!r}.") from exc


def domain_matches(hostname: str, rule: str) -> bool:
    host = normalize_domain(hostname)
    domain = normalize_domain(rule).lstrip(".")
    return bool(domain) and (host == domain or host.endswith(f".{domain}"))


def is_blocked_url(url: str, blocked_domains: list[str]) -> bool:
    host = urlsplit(url).hostname or ""
    return any(domain_matches(host, rule) for rule in blocked_domains)


def _normalize_url(url: str) -> str:
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").encode("idna").decode("ascii").lower()
    netloc = hostname
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def _robots_policy(start_url: str, blocked_domains: list[str]) -> RobotsPolicy:
    parsed = urlsplit(start_url)
    robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    key = (
        "research:robots:v2:"
        + hashlib.sha256(
            f"{robots_url}|{','.join(sorted(blocked_domains))}".encode()
        ).hexdigest()
    )
    cached = cache.get(key)
    if cached:
        parser = None
        if cached["lines"]:
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(cached["lines"])
        return RobotsPolicy(
            parser=parser,
            allow_all=cached["allow_all"],
            sitemaps=tuple(cached["sitemaps"]),
            status_code=cached["status_code"],
        )
    try:
        resource = fetch_public_resource(
            robots_url,
            allowed_content_types={"text/plain", "text/html"},
            max_bytes=settings.CRAWLER_MAX_ROBOTS_BYTES,
            accept="text/plain",
            allowed_statuses={401, 403, 404, 410, 500, 501, 502, 503, 504},
            blocked_domains=blocked_domains,
        )
        status = resource.status_code
        decoded = resource.body.decode(resource.charset, errors="replace")
    except WebPageError:
        status = None
        decoded = ""

    allow_all = status in {404, 410}
    lines = decoded.splitlines() if status is not None and 200 <= status < 300 else []
    sitemaps = tuple(
        line.split(":", 1)[1].strip()
        for line in lines
        if line.lower().startswith("sitemap:") and line.split(":", 1)[1].strip()
    )[: settings.CRAWLER_MAX_SITEMAPS]
    parser = None
    if lines:
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(lines)
    payload = {
        "allow_all": allow_all,
        "lines": lines,
        "sitemaps": list(sitemaps),
        "status_code": status,
    }
    cache.set(key, payload, settings.CRAWLER_ROBOTS_CACHE_SECONDS)
    return RobotsPolicy(
        parser=parser,
        allow_all=allow_all,
        sitemaps=sitemaps,
        status_code=status,
    )


def _sitemap_urls(
    sitemap_url: str, hostname: str, blocked_domains: list[str]
) -> list[str]:
    try:
        resource = fetch_public_resource(
            sitemap_url,
            allowed_content_types={
                "application/xml",
                "text/xml",
                "text/plain",
                "application/octet-stream",
            },
            max_bytes=settings.CRAWLER_MAX_SITEMAP_BYTES,
            accept="application/xml, text/xml, text/plain",
            blocked_domains=blocked_domains,
        )
        root = ElementTree.fromstring(resource.body)
    except (WebPageError, ElementTree.ParseError):
        return []
    urls: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() != "loc" or not element.text:
            continue
        candidate = _normalize_url(element.text.strip())
        if urlsplit(candidate).hostname == hostname:
            urls.append(candidate)
        if len(urls) >= settings.CRAWLER_MAX_SITEMAP_URLS:
            break
    return urls


def _rate_limit(hostname: str, delay_seconds: float) -> None:
    if delay_seconds <= 0:
        return
    key = f"research:rate:v1:{hashlib.sha256(hostname.encode()).hexdigest()}"
    deadline = time.monotonic() + min(delay_seconds * 2, 5)
    while not cache.add(key, "1", timeout=max(1, int(delay_seconds + 0.999))):
        if time.monotonic() >= deadline:
            raise CrawlError("The crawler could not acquire the domain rate-limit slot.")
        time.sleep(min(0.1, delay_seconds))


def _cached_page(
    url: str, *, max_chars: int, blocked_domains: list[str]
) -> tuple[dict[str, Any], bool]:
    key = (
        "research:page:v2:"
        + hashlib.sha256(
            f"{url}|{max_chars}|{','.join(sorted(blocked_domains))}".encode()
        ).hexdigest()
    )
    cached = cache.get(key)
    if cached:
        return cached, True
    page = read_webpage(
        url, max_chars=max_chars, blocked_domains=blocked_domains
    )
    cache.set(key, page, settings.CRAWLER_PAGE_CACHE_SECONDS)
    return page, False


def crawl_website(url: str, *, controls: dict[str, Any] | None = None) -> dict[str, Any]:
    controls = controls or {}
    max_pages = min(max(int(controls.get("max_pages", 10)), 1), settings.CRAWLER_MAX_PAGES)
    max_depth = min(max(int(controls.get("max_depth", 1)), 0), settings.CRAWLER_MAX_DEPTH)
    delay = min(
        max(float(controls.get("rate_limit_seconds", 1)), 0),
        settings.CRAWLER_MAX_RATE_LIMIT_SECONDS,
    )
    max_chars = min(
        max(int(controls.get("max_chars_per_page", 15_000)), 1_000),
        settings.WEB_READER_MAX_TEXT_CHARS,
    )
    blocked_domains = [
        normalize_domain(item) for item in controls.get("blocked_domains", [])[:100]
    ]
    if is_blocked_url(url, blocked_domains):
        raise CrawlError("The requested domain is blocked by the research policy.")

    start = _normalize_url(url)
    start_host = urlsplit(start).hostname or ""
    policy = _robots_policy(start, blocked_domains)
    if not policy.allowed(start):
        raise CrawlError("The website's robots.txt policy does not allow this crawl.")

    queue: deque[tuple[str, int, str]] = deque([(start, 0, "")])
    sitemap_urls = list(policy.sitemaps)
    default_sitemap = urljoin(start, "/sitemap.xml")
    if default_sitemap not in sitemap_urls:
        sitemap_urls.append(default_sitemap)
    for sitemap in sitemap_urls[: settings.CRAWLER_MAX_SITEMAPS]:
        if urlsplit(sitemap).hostname == start_host:
            for candidate in _sitemap_urls(sitemap, start_host, blocked_domains):
                queue.append((candidate, 0, "sitemap"))

    seen_urls: set[str] = set()
    seen_hashes: dict[str, str] = {}
    pages: list[dict[str, Any]] = []
    deadline = time.monotonic() + settings.CRAWLER_MAX_DURATION_SECONDS
    while queue and len(pages) < max_pages and time.monotonic() < deadline:
        current, depth, parent = queue.popleft()
        normalized = _normalize_url(current)
        if normalized in seen_urls:
            continue
        seen_urls.add(normalized)
        if depth > max_depth or urlsplit(normalized).hostname != start_host:
            continue
        if is_blocked_url(normalized, blocked_domains) or not policy.allowed(normalized):
            pages.append(
                {
                    "url": normalized,
                    "parent_url": parent,
                    "depth": depth,
                    "robots_allowed": False,
                    "error": "Blocked by robots.txt or workspace policy.",
                }
            )
            continue
        try:
            _rate_limit(start_host, delay)
            page, from_cache = _cached_page(
                normalized,
                max_chars=max_chars,
                blocked_domains=blocked_domains,
            )
            final_host = urlsplit(page["url"]).hostname or ""
            if final_host != start_host or is_blocked_url(page["url"], blocked_domains):
                raise CrawlError("A page redirected outside the permitted crawl hostname.")
            normalized_text = " ".join(page.get("text", "").split())
            checksum = hashlib.sha256(normalized_text.encode()).hexdigest()
            duplicate_of = seen_hashes.get(checksum)
            if duplicate_of is None:
                seen_hashes[checksum] = page["url"]
            record = {
                **page,
                "parent_url": parent,
                "depth": depth,
                "robots_allowed": True,
                "from_cache": from_cache,
                "checksum": checksum,
                "duplicate_of": duplicate_of,
            }
            pages.append(record)
            if duplicate_of is None and depth < max_depth:
                for link in page.get("links", []):
                    candidate = _normalize_url(link.get("url", ""))
                    if urlsplit(candidate).hostname == start_host and candidate not in seen_urls:
                        queue.append((candidate, depth + 1, page["url"]))
        except (WebPageError, CrawlError) as exc:
            pages.append(
                {
                    "url": normalized,
                    "parent_url": parent,
                    "depth": depth,
                    "robots_allowed": True,
                    "error": str(exc),
                }
            )
    return {
        "start_url": start,
        "robots_status": policy.status_code,
        "sitemaps": sitemap_urls[: settings.CRAWLER_MAX_SITEMAPS],
        "pages": pages,
        "truncated": bool(queue) or time.monotonic() >= deadline,
        "unique_content_pages": len(seen_hashes),
    }
