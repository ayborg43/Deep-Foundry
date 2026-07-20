"""Bounded extraction for public research documents."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from defusedxml import ElementTree
from django.conf import settings
from pypdf import PdfReader

from ai.web_reader import WebPageError, fetch_public_resource, read_webpage


class DocumentReadError(RuntimeError):
    pass


_DOCUMENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/csv",
    "application/csv",
    "text/plain",
    "text/markdown",
    "application/json",
    "application/octet-stream",
    "text/html",
    "application/xhtml+xml",
}


def _bounded_join(segments: list[dict[str, Any]]) -> tuple[str, bool]:
    parts: list[str] = []
    used = 0
    truncated = False
    for segment in segments:
        value = str(segment.get("text", "")).strip()
        if not value:
            continue
        remaining = settings.DOCUMENT_MAX_TEXT_CHARS - used
        if remaining <= 0:
            truncated = True
            break
        if len(value) > remaining:
            value = value[:remaining].rstrip()
            truncated = True
        parts.append(value)
        used += len(value)
    return "\n\n".join(parts), truncated


def _read_pdf(body: bytes) -> list[dict[str, Any]]:
    if not body.startswith(b"%PDF"):
        raise DocumentReadError("The response is not a valid PDF document.")
    try:
        reader = PdfReader(io.BytesIO(body), strict=False)
        if len(reader.pages) > settings.DOCUMENT_MAX_PAGES:
            raise DocumentReadError(
                f"PDF documents are limited to {settings.DOCUMENT_MAX_PAGES} pages."
            )
        return [
            {
                "locator": f"Page {index}",
                "page_number": index,
                "text": (page.extract_text() or "").strip(),
            }
            for index, page in enumerate(reader.pages, start=1)
        ]
    except DocumentReadError:
        raise
    except Exception as exc:
        raise DocumentReadError(f"Could not parse the PDF document: {exc}") from exc


def _read_docx(body: bytes) -> list[dict[str, Any]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(body))
    except zipfile.BadZipFile as exc:
        raise DocumentReadError("The response is not a valid DOCX document.") from exc
    with archive:
        members = archive.infolist()
        if len(members) > settings.DOCUMENT_MAX_ZIP_MEMBERS:
            raise DocumentReadError("The DOCX archive contains too many files.")
        total_size = sum(member.file_size for member in members)
        if total_size > settings.DOCUMENT_MAX_UNCOMPRESSED_BYTES:
            raise DocumentReadError("The DOCX archive expands beyond the configured limit.")
        for member in members:
            if member.compress_size and member.file_size / member.compress_size > 100:
                raise DocumentReadError("The DOCX archive has an unsafe compression ratio.")
            path = PurePosixPath(member.filename)
            if path.is_absolute() or ".." in path.parts:
                raise DocumentReadError("The DOCX archive contains an unsafe path.")
        try:
            xml = archive.read("word/document.xml")
        except KeyError as exc:
            raise DocumentReadError("The DOCX document has no readable body.") from exc
    try:
        root = ElementTree.fromstring(xml)
    except Exception as exc:
        raise DocumentReadError("The DOCX document XML is invalid.") from exc
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t")).strip()
        if text:
            paragraphs.append(text)
    return [{"locator": "Document body", "page_number": None, "text": "\n".join(paragraphs)}]


def _read_csv(body: bytes, charset: str) -> list[dict[str, Any]]:
    decoded = body.decode(charset or "utf-8", errors="replace")
    rows: list[dict[str, Any]] = []
    try:
        reader = csv.reader(io.StringIO(decoded))
        for row_number, row in enumerate(reader, start=1):
            if row_number > settings.DOCUMENT_MAX_CSV_ROWS:
                break
            cells = [cell[: settings.DOCUMENT_MAX_CELL_CHARS] for cell in row[:100]]
            rows.append(
                {
                    "locator": f"Row {row_number}",
                    "page_number": None,
                    "text": " | ".join(cells),
                }
            )
    except csv.Error as exc:
        raise DocumentReadError(f"Could not parse the CSV document: {exc}") from exc
    return rows


def read_public_document(
    url: str, *, blocked_domains: list[str] | None = None
) -> dict[str, Any]:
    suffix = PurePosixPath(urlsplit(str(url)).path).suffix.lower()
    if suffix in {".html", ".htm"}:
        return read_webpage(url, blocked_domains=blocked_domains)
    try:
        resource = fetch_public_resource(
            url,
            allowed_content_types=_DOCUMENT_TYPES,
            max_bytes=settings.WEB_DOCUMENT_MAX_RESPONSE_BYTES,
            accept=(
                "application/pdf, "
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document, "
                "text/csv, application/json, text/plain, text/html;q=0.8"
            ),
            blocked_domains=blocked_domains,
        )
    except WebPageError as exc:
        raise DocumentReadError(str(exc)) from exc

    content_type = resource.content_type
    if content_type == "application/pdf" or suffix == ".pdf":
        segments = _read_pdf(resource.body)
        kind = "pdf"
    elif (
        content_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        or suffix == ".docx"
    ):
        segments = _read_docx(resource.body)
        kind = "docx"
    elif content_type in {"text/csv", "application/csv"} or suffix == ".csv":
        segments = _read_csv(resource.body, resource.charset)
        kind = "csv"
    elif content_type == "application/json" or suffix == ".json":
        try:
            value = json.loads(resource.body.decode(resource.charset, errors="replace"))
        except (json.JSONDecodeError, LookupError) as exc:
            raise DocumentReadError("The JSON document is invalid.") from exc
        segments = [
            {
                "locator": "JSON document",
                "page_number": None,
                "text": json.dumps(value, ensure_ascii=False, indent=2),
            }
        ]
        kind = "json"
    elif content_type in {"text/html", "application/xhtml+xml"}:
        return read_webpage(url, blocked_domains=blocked_domains)
    else:
        try:
            decoded = resource.body.decode(resource.charset, errors="replace")
        except LookupError:
            decoded = resource.body.decode("utf-8", errors="replace")
        segments = [{"locator": "Document body", "page_number": None, "text": decoded.strip()}]
        kind = "text"

    text, truncated = _bounded_join(segments)
    if truncated:
        text += "\n\n[Content truncated at the configured limit.]"
    return {
        "requested_url": resource.requested_url,
        "url": resource.final_url,
        "canonical_url": "",
        "status_code": resource.status_code,
        "content_type": resource.content_type,
        "document_type": kind,
        "language": "",
        "title": PurePosixPath(urlsplit(resource.final_url).path).name or resource.final_url,
        "description": "",
        "publisher": "",
        "published_at": "",
        "last_modified": resource.headers.get("last-modified", ""),
        "text": text,
        "segments": segments,
        "headings": [],
        "links": [],
        "truncated": truncated,
    }
