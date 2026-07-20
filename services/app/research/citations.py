from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, time
from urllib.parse import urlsplit

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from ai.models import Message
from research.models import MessageCitation, ResearchEvidence, ResearchSource


def _published(value):
    raw = str(value or "")
    parsed = parse_datetime(raw)
    if parsed:
        return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)
    parsed_date = parse_date(raw[:10])
    if parsed_date:
        return timezone.make_aware(
            datetime.combine(parsed_date, time.min)
        )
    return None


def _passage(text: str, query: str) -> str:
    terms = set(re.findall(r"[A-Za-z0-9]{3,}", query.lower()))
    candidates = [
        " ".join(part.split())
        for part in re.split(r"\n\s*\n|\n", text)
        if len(" ".join(part.split())) >= 30
    ]
    if not candidates:
        return " ".join(text.split())[:900]
    return max(
        candidates,
        key=lambda item: (
            len(terms & set(re.findall(r"[A-Za-z0-9]{3,}", item.lower()))),
            len(item),
        ),
    )[:900]


def _page_candidates(result: dict) -> list[dict]:
    if isinstance(result.get("pages"), list):
        return [value for value in result["pages"] if isinstance(value, dict)]
    if result.get("url") and result.get("text"):
        return [result]
    # Search-provider snippets are discovery hints, not verified source
    # passages. A coworker must open a result before it can become evidence.
    return []


def _claim_for_ordinal(content: str, ordinal: int) -> str:
    marker = f"[S{ordinal}]"
    claims = []
    for section in re.split(r"(?<=[.!?])\s+|\n+", content):
        if marker not in section:
            continue
        value = re.sub(r"\[S\d+\]", "", section)
        value = re.sub(r"^[#>*\-\d.\s]+", "", value).strip()
        value = re.sub(r"\s+([.,;:!?])", r"\1", value)
        if value:
            claims.append(value)
    return " ".join(dict.fromkeys(claims))[:2000]


def attach_message_citations(message: Message, *, query: str) -> list[MessageCitation]:
    if message.citations.exists():
        return list(message.citations.select_related("evidence__source"))
    tool_results = (
        Message.objects.filter(
            conversation=message.conversation,
            sender_type=Message.SenderType.SYSTEM,
            tool_call_id__isnull=False,
            created_at__lte=message.created_at,
        )
        .order_by("created_at")
    )
    latest_user = (
        message.conversation.messages.filter(
            sender_type=Message.SenderType.USER,
            created_at__lte=message.created_at,
        )
        .order_by("-created_at")
        .first()
    )
    if latest_user:
        tool_results = tool_results.filter(created_at__gte=latest_user.created_at)

    pages: list[dict] = []
    for row in tool_results:
        try:
            result = json.loads(row.content)
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict):
            pages.extend(_page_candidates(result))

    citations: list[MessageCitation] = []
    seen: set[tuple[str, str]] = set()
    cited_ordinals = {int(value) for value in re.findall(r"\[S(\d+)\]", message.content)}
    for source_ordinal, page in enumerate(pages, start=1):
        if source_ordinal not in cited_ordinals:
            continue
        url = str(page.get("url") or page.get("requested_url") or "")
        text = str(page.get("text") or "").strip()
        if not url.startswith(("http://", "https://")) or not text:
            continue
        normalized = " ".join(text.split())
        checksum = hashlib.sha256(normalized.encode()).hexdigest()
        key = (url, checksum)
        if key in seen:
            continue
        seen.add(key)
        host = urlsplit(url).hostname or ""
        source = ResearchSource.objects.create(
            source_type=(
                ResearchSource.SourceType.DOCUMENT
                if page.get("document_type")
                else ResearchSource.SourceType.WEBPAGE
            ),
            requested_url=str(page.get("requested_url") or url),
            url=url,
            canonical_url=str(page.get("canonical_url") or ""),
            title=str(page.get("title") or host)[:500],
            publisher=str(page.get("publisher") or "")[:255],
            published_at=_published(page.get("published_at")),
            language=str(page.get("language") or "")[:30],
            country="",
            content_type=str(page.get("content_type") or "")[:255],
            checksum=checksum,
            text=text,
            metadata={
                "segments": page.get("segments", []),
                "last_modified": page.get("last_modified", ""),
            },
        )
        supporting = _passage(text, query)
        if supporting not in text:
            source.delete()
            continue
        locator = ""
        page_number = None
        for segment in page.get("segments", []):
            if supporting[:80] in str(segment.get("text", "")):
                locator = str(segment.get("locator", ""))[:255]
                page_number = segment.get("page_number")
                break
        ordinal = source_ordinal
        evidence = ResearchEvidence(
            source=source,
            ordinal=ordinal,
            passage=supporting,
            locator=locator,
            page_number=page_number,
        )
        evidence.full_clean()
        evidence.save()
        citations.append(
            MessageCitation.objects.create(
                message=message,
                evidence=evidence,
                ordinal=ordinal,
                claim=_claim_for_ordinal(message.content, ordinal),
            )
        )
    return citations
