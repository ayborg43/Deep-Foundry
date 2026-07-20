"""Bounded, SSRF-resistant public webpage reader.

The reader resolves and pins a public IP before connecting, validates every
redirect, accepts only textual response types, and limits both downloaded and
model-facing content. It intentionally does not execute JavaScript, submit
forms, retain cookies, or authenticate to websites.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import time
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from django.conf import settings


class WebPageError(RuntimeError):
    pass


@dataclass(frozen=True)
class PublicResource:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    charset: str
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)


# Compatibility for existing tests and internal callers while the public
# fetch primitive now has a clearer name.
_FetchedPage = PublicResource


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, resolved_ip: str, port: int, *, timeout: float) -> None:
        super().__init__(host, port=port, timeout=timeout)
        self._resolved_ip = resolved_ip

    def connect(self) -> None:
        self.sock = socket.create_connection(
            (self._resolved_ip, self.port),
            self.timeout,
            self.source_address,
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, resolved_ip: str, port: int, *, timeout: float) -> None:
        super().__init__(
            host,
            port=port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        self._resolved_ip = resolved_ip

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (self._resolved_ip, self.port),
            self.timeout,
            self.source_address,
        )
        self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)


def _validated_target(url: str) -> tuple[Any, str, int]:
    value = str(url or "").strip()
    if not value:
        raise WebPageError("read_webpage requires a URL.")
    if len(value) > 2048:
        raise WebPageError("Webpage URLs are limited to 2,048 characters.")
    if any(ord(character) < 32 for character in value):
        raise WebPageError("The webpage URL contains invalid control characters.")

    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise WebPageError("Only public HTTP and HTTPS webpages can be read.")
    if parsed.username is not None or parsed.password is not None:
        raise WebPageError("Webpage URLs cannot contain embedded credentials.")
    if not parsed.hostname:
        raise WebPageError("The webpage URL must include a hostname.")

    default_port = 443 if scheme == "https" else 80
    try:
        port = parsed.port or default_port
    except ValueError as exc:
        raise WebPageError("The webpage URL contains an invalid port.") from exc
    if port != default_port:
        raise WebPageError("Webpage requests are limited to the standard HTTP and HTTPS ports.")

    hostname = parsed.hostname.rstrip(".")
    try:
        hostname_ascii = hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise WebPageError("The webpage hostname is invalid.") from exc

    try:
        addresses = socket.getaddrinfo(
            hostname_ascii,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise WebPageError(f"Could not resolve webpage hostname {hostname!r}.") from exc

    resolved: list[str] = []
    for address in addresses:
        candidate = address[4][0]
        if candidate not in resolved:
            resolved.append(candidate)
    if not resolved:
        raise WebPageError(f"Could not resolve webpage hostname {hostname!r}.")
    for candidate in resolved:
        try:
            public = ipaddress.ip_address(candidate).is_global
        except ValueError as exc:
            raise WebPageError("The webpage hostname resolved to an invalid address.") from exc
        if not public:
            raise WebPageError(
                "Webpage requests to private, loopback, link-local, or reserved networks are blocked."
            )
    preferred = next(
        (candidate for candidate in resolved if ipaddress.ip_address(candidate).version == 4),
        resolved[0],
    )
    return parsed, preferred, port


def validate_public_url(url: str) -> str:
    """Validate and normalize a user-supplied public URL without fetching it."""
    parsed, _, _ = _validated_target(url)
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc,
            parsed.path or "/",
            parsed.query,
            "",
        )
    )


def _blocked_by_domain_policy(url: str, blocked_domains: list[str] | None) -> bool:
    if not blocked_domains:
        return False
    host = (urlsplit(url).hostname or "").rstrip(".").lower()
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return True
    for raw_rule in blocked_domains[:100]:
        rule = str(raw_rule or "").strip().lower().lstrip(".").rstrip(".")
        if "://" in rule:
            rule = (urlsplit(rule).hostname or "").lower()
        try:
            rule = rule.encode("idna").decode("ascii")
        except UnicodeError:
            continue
        if rule and (host == rule or host.endswith(f".{rule}")):
            return True
    return False


def _request_once(
    url: str,
    *,
    max_bytes: int,
    accept: str,
    deadline: float,
) -> tuple[int, dict[str, str], bytes]:
    parsed, resolved_ip, port = _validated_target(url)
    hostname = parsed.hostname.rstrip(".").encode("idna").decode("ascii")
    host_header = f"[{hostname}]" if ":" in hostname else hostname
    connection_type = (
        _PinnedHTTPSConnection if parsed.scheme.lower() == "https" else _PinnedHTTPConnection
    )
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise WebPageError("The webpage request exceeded the total time limit.")
    connection = connection_type(
        hostname,
        resolved_ip,
        port,
        timeout=min(settings.WEB_READER_TIMEOUT_SECONDS, remaining),
    )
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    headers = {
        "Accept": accept,
        "Accept-Encoding": "identity",
        "Connection": "close",
        "Host": host_header,
        "User-Agent": settings.WEB_READER_USER_AGENT,
    }
    try:
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        response_headers = {key.lower(): value for key, value in response.getheaders()}
        content_length = response_headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > max_bytes:
                    raise WebPageError("The webpage response exceeds the configured size limit.")
            except ValueError:
                pass
        chunks: list[bytes] = []
        total = 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WebPageError("The webpage request exceeded the total time limit.")
            if connection.sock is not None:
                connection.sock.settimeout(
                    min(settings.WEB_READER_TIMEOUT_SECONDS, remaining)
                )
            chunk = response.read1(min(64 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise WebPageError("The webpage response exceeds the configured size limit.")
        return response.status, response_headers, b"".join(chunks)
    except (OSError, http.client.HTTPException, TimeoutError) as exc:
        raise WebPageError(f"The webpage request failed: {exc}") from exc
    finally:
        connection.close()


def fetch_public_resource(
    url: str,
    *,
    allowed_content_types: set[str],
    max_bytes: int | None = None,
    accept: str = "*/*",
    allowed_statuses: set[int] | None = None,
    blocked_domains: list[str] | None = None,
) -> PublicResource:
    """Fetch one public resource through the shared SSRF-resistant boundary.

    Callers provide an explicit MIME allowlist and size bound. Every redirect
    is resolved and revalidated, and one wall-clock deadline covers the entire
    redirect chain.
    """
    requested_url = str(url).strip()
    current_url = requested_url
    redirects = 0
    byte_limit = max_bytes or settings.WEB_READER_MAX_RESPONSE_BYTES
    if byte_limit < 1 or byte_limit > settings.WEB_DOCUMENT_MAX_RESPONSE_BYTES:
        raise WebPageError("The requested response-size limit is invalid.")
    deadline = time.monotonic() + settings.WEB_FETCH_TOTAL_TIMEOUT_SECONDS
    accepted_statuses = allowed_statuses or set()
    while True:
        if time.monotonic() >= deadline:
            raise WebPageError("The webpage request exceeded the total time limit.")
        if _blocked_by_domain_policy(current_url, blocked_domains):
            raise WebPageError("The destination is blocked by the workspace research policy.")
        status, headers, body = _request_once(
            current_url,
            max_bytes=byte_limit,
            accept=accept,
            deadline=deadline,
        )
        if status in {301, 302, 303, 307, 308}:
            location = headers.get("location")
            if not location:
                raise WebPageError("The webpage returned a redirect without a destination.")
            redirects += 1
            if redirects > settings.WEB_READER_MAX_REDIRECTS:
                raise WebPageError("The webpage exceeded the configured redirect limit.")
            redirected_url = urljoin(current_url, location)
            if (
                urlsplit(current_url).scheme.lower() == "https"
                and urlsplit(redirected_url).scheme.lower() == "http"
            ):
                raise WebPageError("HTTPS webpages cannot redirect to insecure HTTP.")
            current_url = redirected_url
            _validated_target(current_url)
            if _blocked_by_domain_policy(current_url, blocked_domains):
                raise WebPageError(
                    "The redirect destination is blocked by the workspace research policy."
                )
            continue
        if (status < 200 or status >= 300) and status not in accepted_statuses:
            raise WebPageError(f"The webpage returned HTTP {status}.")

        encoding = headers.get("content-encoding", "identity").lower()
        if encoding not in {"", "identity"}:
            raise WebPageError(f"Unsupported webpage content encoding {encoding!r}.")
        raw_content_type = headers.get("content-type", "text/html")
        media_type = raw_content_type.split(";", 1)[0].strip().lower()
        if media_type not in allowed_content_types:
            raise WebPageError(
                f"Unsupported webpage content type {media_type!r}."
            )
        charset = "utf-8"
        for parameter in raw_content_type.split(";")[1:]:
            key, separator, value = parameter.strip().partition("=")
            if separator and key.lower() == "charset" and value.strip():
                charset = value.strip().strip("\"'")
                break
        return PublicResource(
            requested_url=requested_url,
            final_url=current_url,
            status_code=status,
            content_type=media_type,
            charset=charset,
            body=body,
            headers=headers,
        )


def _fetch_url(
    url: str, *, blocked_domains: list[str] | None = None
) -> PublicResource:
    return fetch_public_resource(
        url,
        allowed_content_types={
            "text/html",
            "application/xhtml+xml",
            "text/plain",
            "application/json",
        },
        accept="text/html, application/xhtml+xml, text/plain, application/json;q=0.9",
        blocked_domains=blocked_domains,
    )


_BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "dd",
    "div",
    "dl",
    "dt",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}
_IGNORED_TAGS = {"canvas", "noscript", "script", "style", "svg", "template"}


def _clean_text(parts: list[str]) -> str:
    lines = [" ".join(line.split()) for line in "".join(parts).splitlines()]
    result: list[str] = []
    for line in lines:
        if line:
            result.append(line)
        elif result and result[-1] != "":
            result.append("")
    return "\n".join(result).strip()


class _ReadableHTMLParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self.description = ""
        self.canonical_url = ""
        self.language = ""
        self.publisher = ""
        self.published_at = ""
        self.headings: list[dict[str, str | int]] = []
        self.links: list[dict[str, str]] = []
        self._all_parts: list[str] = []
        self._preferred_parts: list[str] = []
        self._preferred_depth = 0
        self._ignored_depth = 0
        self._in_title = False
        self._title_parts: list[str] = []
        self._heading_level: int | None = None
        self._heading_parts: list[str] = []
        self._link_url = ""
        self._link_parts: list[str] = []
        self._seen_links: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = {key.lower(): value or "" for key, value in attrs}
        if tag in _IGNORED_TAGS:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == "html":
            self.language = values.get("lang", "")[:30]
        if tag in {"main", "article"}:
            self._preferred_depth += 1
        if tag in _BLOCK_TAGS:
            self._append("\n")
        if tag == "title":
            self._in_title = True
            self._title_parts = []
        elif tag == "meta":
            name = values.get("name", "").lower()
            property_name = values.get("property", "").lower()
            if name == "description" or property_name == "og:description":
                if not self.description:
                    self.description = " ".join(values.get("content", "").split())[:1000]
            if name in {"author", "publisher", "application-name"} or property_name in {
                "og:site_name",
                "article:publisher",
            }:
                if not self.publisher:
                    self.publisher = " ".join(values.get("content", "").split())[:255]
            if name in {"date", "datepublished", "pubdate", "publish-date"} or property_name in {
                "article:published_time",
                "og:published_time",
            }:
                if not self.published_at:
                    self.published_at = values.get("content", "").strip()[:100]
        elif tag == "link" and "canonical" in values.get("rel", "").lower().split():
            candidate = urljoin(self.base_url, values.get("href", ""))
            if urlsplit(candidate).scheme in {"http", "https"}:
                self.canonical_url = candidate
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._heading_level = int(tag[1])
            self._heading_parts = []
        elif tag == "a":
            self._link_url = values.get("href", "")
            self._link_parts = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _IGNORED_TAGS:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if tag == "title" and self._in_title:
            self.title = " ".join("".join(self._title_parts).split())[:500]
            self._in_title = False
        elif self._heading_level is not None and tag == f"h{self._heading_level}":
            text = " ".join("".join(self._heading_parts).split())
            if text and len(self.headings) < settings.WEB_READER_MAX_HEADINGS:
                self.headings.append({"level": self._heading_level, "text": text[:500]})
            self._heading_level = None
            self._heading_parts = []
        elif tag == "a" and self._link_url:
            candidate = urljoin(self.base_url, self._link_url)
            parsed = urlsplit(candidate)
            if parsed.scheme in {"http", "https"} and parsed.hostname:
                normalized = urlunsplit(
                    (parsed.scheme, parsed.netloc, parsed.path, parsed.query, "")
                )
                if (
                    normalized not in self._seen_links
                    and len(self.links) < settings.WEB_READER_MAX_LINKS
                ):
                    self._seen_links.add(normalized)
                    self.links.append(
                        {
                            "text": " ".join("".join(self._link_parts).split())[:300],
                            "url": normalized,
                        }
                    )
            self._link_url = ""
            self._link_parts = []
        if tag in _BLOCK_TAGS:
            self._append("\n")
        if tag in {"main", "article"} and self._preferred_depth:
            self._preferred_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        self._append(data)
        if self._in_title:
            self._title_parts.append(data)
        if self._heading_level is not None:
            self._heading_parts.append(data)
        if self._link_url:
            self._link_parts.append(data)

    def _append(self, value: str) -> None:
        self._all_parts.append(value)
        if self._preferred_depth:
            self._preferred_parts.append(value)

    def readable_text(self) -> str:
        preferred = _clean_text(self._preferred_parts)
        return preferred or _clean_text(self._all_parts)


def read_webpage(
    url: str,
    *,
    max_chars: int | None = None,
    blocked_domains: list[str] | None = None,
) -> dict[str, Any]:
    limit = max_chars if max_chars is not None else settings.WEB_READER_MAX_TEXT_CHARS
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise WebPageError("max_chars must be an integer.")
    if limit < 1000 or limit > settings.WEB_READER_MAX_TEXT_CHARS:
        raise WebPageError(
            f"max_chars must be between 1,000 and {settings.WEB_READER_MAX_TEXT_CHARS:,}."
        )

    fetched = _fetch_url(url, blocked_domains=blocked_domains)
    try:
        decoded = fetched.body.decode(fetched.charset, errors="replace")
    except LookupError:
        decoded = fetched.body.decode("utf-8", errors="replace")

    title = ""
    description = ""
    canonical_url = ""
    language = ""
    headings: list[dict[str, str | int]] = []
    links: list[dict[str, str]] = []
    publisher = ""
    published_at = ""
    if fetched.content_type in {"text/html", "application/xhtml+xml"}:
        parser = _ReadableHTMLParser(fetched.final_url)
        parser.feed(decoded)
        parser.close()
        text = parser.readable_text()
        title = parser.title
        description = parser.description
        canonical_url = parser.canonical_url
        language = parser.language
        headings = parser.headings
        links = parser.links
        publisher = parser.publisher
        published_at = parser.published_at
    else:
        text = decoded.strip()

    truncated = len(text) > limit
    if truncated:
        text = text[:limit].rstrip() + "\n\n[Content truncated at the configured limit.]"
    return {
        "requested_url": fetched.requested_url,
        "url": fetched.final_url,
        "canonical_url": canonical_url,
        "status_code": fetched.status_code,
        "content_type": fetched.content_type,
        "language": language,
        "title": title,
        "description": description,
        "publisher": publisher,
        "published_at": published_at,
        "accessed_at": datetime.now().astimezone().isoformat(),
        "last_modified": fetched.headers.get("last-modified", ""),
        "text": text,
        "headings": headings,
        "links": links,
        "truncated": truncated,
    }
