from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, time, timedelta
from difflib import unified_diff
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from ai.browser_reader import BrowserReadError, browse_webpage
from ai.document_reader import DocumentReadError, read_public_document
from ai.model_router.factory import build_model_router
from ai.model_router.types import ChatMessage, ModelConfig
from ai.structured_extraction import (
    ExtractionError,
    extract_labeled_values,
    parse_model_json,
    validate_field_schema,
)
from ai.web_crawler import CrawlError, crawl_website, domain_matches, is_blocked_url
from ai.web_search import WebSearchError, search_web
from core.interface import write_audit_log
from core.models import Coworker, Notification
from research.models import (
    CrawlPage,
    ResearchEvidence,
    ResearchRun,
    ResearchSource,
    ResearchStep,
    StructuredExtraction,
    WebsiteMonitor,
    WebsiteMonitorRun,
    WebsiteSnapshot,
)


def _notify_user(*, user_id, workspace_id, notification_type: str, payload: dict) -> None:
    notification = Notification.objects.create(
        workspace_id=workspace_id,
        user_id=user_id,
        type=notification_type,
        payload=payload,
    )
    from worker.tasks import enqueue_notification_deliveries

    enqueue_notification_deliveries(str(notification.id))


def _set_stage(run: ResearchRun, stage: str, progress: int, message: str, **details) -> None:
    sequence = (run.steps.aggregate(value=Max("sequence"))["value"] or 0) + 1
    ResearchStep.objects.create(
        run=run,
        sequence=sequence,
        stage=stage,
        status=ResearchStep.Status.COMPLETED,
        message=message[:500],
        details=details,
    )
    run.status = stage if stage in ResearchRun.Status.values else run.status
    run.current_stage = stage
    run.progress = min(max(progress, 0), 100)
    run.save(update_fields=["status", "current_stage", "progress", "updated_at"])


def _check_cancelled(run: ResearchRun) -> None:
    run.refresh_from_db(fields=["cancel_requested"])
    if run.cancel_requested:
        run.status = ResearchRun.Status.CANCELLED
        run.current_stage = "cancelled"
        run.completed_at = timezone.now()
        run.save(
            update_fields=["status", "current_stage", "completed_at", "updated_at"]
        )
        raise InterruptedError("Research was cancelled.")


def _parse_json_object(content: str) -> dict | list:
    text = str(content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _router_for(run: ResearchRun):
    binding = (
        run.coworker.current_version.model_binding
        if run.coworker_id and run.coworker.current_version
        else {"primary": "deepseek-v4-flash", "deployment_mode": "deepseek_cloud"}
    )
    return (
        build_model_router(
            workspace_id=run.workspace_id,
            coworker_id=run.coworker_id,
            model_binding=binding,
        ),
        binding,
    )


def _generate(run: ResearchRun, system: str, user: str, *, max_tokens: int = 4000) -> str:
    router, binding = _router_for(run)
    response = router.generate(
        [
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=user),
        ],
        [],
        ModelConfig(
            model_id=binding.get("primary", "deepseek-v4-flash"),
            temperature=0.2,
            max_tokens=max_tokens,
        ),
        fallback_model_id=(binding.get("fallback") or [None])[0],
    )
    return response.content


def _fallback_plan(query: str) -> list[str]:
    return [
        query,
        f"{query} primary sources",
        f"{query} recent evidence",
    ]


def _plan_queries(run: ResearchRun) -> list[str]:
    try:
        content = _generate(
            run,
            (
                "You plan evidence-based web research. Return only a JSON array of "
                "3 to 5 concise, non-duplicative search queries. Do not include URLs."
            ),
            run.query,
            max_tokens=800,
        )
        value = _parse_json_object(content)
        if not isinstance(value, list):
            raise ValueError
        queries = [str(item).strip()[:500] for item in value if str(item).strip()]
        return queries[:5] or _fallback_plan(run.query)
    except Exception:
        return _fallback_plan(run.query)


def _publication_datetime(value: str):
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is not None:
        return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)
    parsed_date = parse_date(value[:10])
    if parsed_date is not None:
        return timezone.make_aware(
            datetime.combine(parsed_date, time.min)
        )
    return None


def _country_from_host(host: str) -> str:
    suffix = host.rsplit(".", 1)[-1].upper() if "." in host else ""
    return suffix if len(suffix) == 2 else ""


def _best_passage(text: str, query: str) -> tuple[str, float]:
    paragraphs = [
        " ".join(value.split())
        for value in re.split(r"\n\s*\n|\n", text)
        if len(" ".join(value.split())) >= 40
    ]
    if not paragraphs:
        return " ".join(text.split())[:700], 0
    terms = {term.lower() for term in re.findall(r"[A-Za-z0-9]{3,}", query)}
    scored = []
    for paragraph in paragraphs:
        words = set(re.findall(r"[A-Za-z0-9]{3,}", paragraph.lower()))
        score = len(terms & words) / max(len(terms), 1)
        scored.append((score, paragraph))
    score, passage = max(scored, key=lambda item: (item[0], len(item[1])))
    return passage[:900], score


def _store_source(run: ResearchRun, page: dict, source_type: str) -> ResearchSource | None:
    text = str(page.get("text", "")).strip()
    if not text:
        return None
    normalized = " ".join(text.split())
    checksum = hashlib.sha256(normalized.encode()).hexdigest()
    duplicate = run.sources.filter(checksum=checksum, duplicate_of__isnull=True).first()
    final_url = str(page.get("url") or page.get("requested_url") or "")
    host = urlsplit(final_url).hostname or ""
    controls = run.controls
    if is_blocked_url(final_url, controls.get("blocked_domains", [])):
        return None
    requested_language = str(controls.get("language") or "").strip().lower()
    source_language = str(page.get("language") or "").strip().lower()
    if requested_language and source_language and not source_language.startswith(
        requested_language
    ):
        return None
    requested_country = str(controls.get("country") or "").strip().upper()
    discovered_country = str(page.get("country") or "").strip().upper()
    source_country = (
        discovered_country if 1 < len(discovered_country) <= 3 else _country_from_host(host)
    )
    if requested_country and source_country and source_country != requested_country:
        return None
    published_at = _publication_datetime(str(page.get("published_at") or ""))
    if controls.get("recency_days") and published_at:
        cutoff = timezone.now() - timedelta(
            days=min(max(int(controls["recency_days"]), 1), 3650)
        )
        if published_at < cutoff:
            return None
    source = ResearchSource.objects.create(
        run=run,
        source_type=source_type,
        requested_url=str(page.get("requested_url") or final_url),
        url=final_url,
        canonical_url=str(page.get("canonical_url") or ""),
        title=str(page.get("title") or host)[:500],
        publisher=str(page.get("publisher") or "")[:255],
        published_at=published_at,
        language=str(page.get("language") or "")[:30],
        country=source_country,
        content_type=str(page.get("content_type") or "")[:255],
        checksum=checksum,
        text=text,
        metadata={
            "description": page.get("description", ""),
            "headings": page.get("headings", []),
            "segments": page.get("segments", []),
            "last_modified": page.get("last_modified", ""),
            "truncated": bool(page.get("truncated")),
            "discovery_provider": page.get("discovery_provider", ""),
            "discovery_country": page.get("discovery_country", ""),
        },
        duplicate_of=duplicate,
    )
    return source


def _evidence_for_sources(run: ResearchRun) -> list[ResearchEvidence]:
    evidence: list[ResearchEvidence] = []
    ordinal = 1
    for source in run.sources.filter(duplicate_of__isnull=True):
        passage, relevance = _best_passage(source.text, run.query)
        if not passage or passage not in source.text:
            continue
        locator = ""
        page_number = None
        for segment in source.metadata.get("segments", []):
            if passage[:80] and passage[:80] in str(segment.get("text", "")):
                locator = str(segment.get("locator", ""))[:255]
                page_number = segment.get("page_number")
                break
        row = ResearchEvidence.objects.create(
            source=source,
            ordinal=ordinal,
            passage=passage,
            locator=locator,
            page_number=page_number,
            relevance=relevance,
        )
        evidence.append(row)
        ordinal += 1
    return evidence


def _detect_conflicts(run: ResearchRun, evidence: list[ResearchEvidence]) -> list[dict]:
    if len(evidence) < 2:
        return []
    evidence_text = "\n".join(
        f"[S{item.ordinal}] {item.passage}" for item in evidence[:12]
    )
    try:
        content = _generate(
            run,
            (
                "Compare evidence for material factual conflicts. Return only a JSON array. "
                "Each item must be {\"claim\":\"...\",\"sources\":[1,2],"
                "\"explanation\":\"...\"}. Return [] when evidence differs only in emphasis. "
                "Use only the supplied source numbers."
            ),
            f"Research question: {run.query}\n\n{evidence_text}",
            max_tokens=1500,
        )
        value = _parse_json_object(content)
        valid_ordinals = {item.ordinal for item in evidence}
        if not isinstance(value, list):
            return []
        return [
            {
                "claim": str(item.get("claim", ""))[:500],
                "sources": [int(value) for value in item.get("sources", []) if int(value) in valid_ordinals],
                "explanation": str(item.get("explanation", ""))[:1000],
            }
            for item in value[:20]
            if isinstance(item, dict)
        ]
    except Exception:
        return []


def _quality(run: ResearchRun, evidence: list[ResearchEvidence], conflicts: list[dict]) -> list[str]:
    controls = run.controls
    reasons: list[str] = []
    hosts = {
        urlsplit(item.source.url).hostname
        for item in evidence
        if urlsplit(item.source.url).hostname
    }
    minimum = min(max(int(controls.get("minimum_sources", 3)), 1), 10)
    if len(hosts) < minimum:
        reasons.append(
            f"Only {len(hosts)} independent source domain(s) were available; {minimum} requested."
        )
    if len(evidence) < 2:
        reasons.append("Important findings are not corroborated by multiple sources.")
    if conflicts:
        reasons.append("Sources contain material conflicts that require user judgment.")
    requested_language = str(controls.get("language") or "").strip().lower()
    if requested_language and any(
        not item.source.language
        for item in evidence
    ):
        reasons.append(
            "The requested language could not be verified for every supporting source."
        )
    requested_country = str(controls.get("country") or "").strip().upper()
    if requested_country and any(
        not item.source.country
        for item in evidence
    ):
        reasons.append(
            "The requested country could not be verified for every supporting source."
        )
    recency_days = controls.get("recency_days")
    if recency_days:
        cutoff = timezone.now() - timedelta(days=min(max(int(recency_days), 1), 3650))
        dated = [item.source for item in evidence if item.source.published_at]
        if len(dated) < len(evidence):
            reasons.append(
                "Publication dates were unavailable for some sources, so recency is only partially verified."
            )
        if dated and all(item.published_at < cutoff for item in dated):
            reasons.append("All dated sources are older than the requested recency window.")
    return reasons


def _write_report(
    run: ResearchRun,
    evidence: list[ResearchEvidence],
    conflicts: list[dict],
    weak_reasons: list[str],
) -> str:
    supplied = "\n\n".join(
        (
            f"[S{item.ordinal}] {item.source.title}\n"
            f"URL: {item.source.url}\n"
            f"Published: {item.source.published_at or 'Unknown'}\n"
            f"Evidence: {item.passage}"
        )
        for item in evidence[:15]
    )
    try:
        report = _generate(
            run,
            (
                "Write a concise, structured research report in Markdown. Every material "
                "factual claim must cite one or more supplied sources using [S1] notation. "
                "Compare disagreement explicitly. Never create a URL, source number, quote, "
                "or fact not present in the evidence. End with Limitations when evidence is weak."
            ),
            (
                f"Question: {run.query}\n\nEvidence:\n{supplied}\n\n"
                f"Detected conflicts: {json.dumps(conflicts)}\n"
                f"Quality warnings: {json.dumps(weak_reasons)}"
            ),
            max_tokens=5000,
        )
    except Exception:
        lines = [f"# Research report\n\n{run.query}\n", "## Evidence"]
        lines.extend(
            f"- {item.passage} [S{item.ordinal}]" for item in evidence
        )
        if weak_reasons:
            lines.append("\n## Limitations")
            lines.extend(f"- {reason}" for reason in weak_reasons)
        report = "\n".join(lines)
    valid = {str(item.ordinal) for item in evidence}
    report = re.sub(
        r"\[S(\d+)\]",
        lambda match: match.group(0) if match.group(1) in valid else "",
        report,
    )
    if evidence and not re.search(r"\[S\d+\]", report):
        report += "\n\n## Sources\n" + "\n".join(
            f"- [S{item.ordinal}] {item.source.title}" for item in evidence
        )
    return report


def _bind_report_claims(report: str, evidence: list[ResearchEvidence]) -> None:
    """Persist the report claims that each exact retained passage supports."""
    by_ordinal = {item.ordinal: item for item in evidence}
    claims: dict[int, list[str]] = {}
    for section in re.split(r"(?<=[.!?])\s+|\n+", report):
        ordinals = {int(value) for value in re.findall(r"\[S(\d+)\]", section)}
        if not ordinals:
            continue
        claim = re.sub(r"\[S\d+\]", "", section)
        claim = re.sub(r"^[#>*\-\d.\s]+", "", claim).strip()
        claim = re.sub(r"\s+([.,;:!?])", r"\1", claim)
        if not claim:
            continue
        for ordinal in ordinals:
            if ordinal in by_ordinal:
                claims.setdefault(ordinal, []).append(claim)
    for ordinal, item in by_ordinal.items():
        unique = list(dict.fromkeys(claims.get(ordinal, [])))
        item.claim = " ".join(unique)[:2000]
        item.save(update_fields=["claim"])


def _run_extraction(run: ResearchRun, evidence: list[ResearchEvidence]) -> None:
    raw_schema = run.controls.get("extraction_schema")
    if not raw_schema:
        return
    schema = validate_field_schema(raw_schema)
    source_text = "\n\n".join(
        f"[S{item.ordinal}] {item.passage}" for item in evidence
    )[: settings.EXTRACTION_MAX_INPUT_CHARS]
    warnings: list[str] = []
    try:
        content = _generate(
            run,
            (
                "Extract the requested fields from the supplied evidence. Return only one "
                "JSON object with exactly the requested keys. Use empty values when absent; "
                "do not infer or invent values."
            ),
            f"Schema examples: {json.dumps(schema)}\n\nEvidence:\n{source_text}",
            max_tokens=2500,
        )
        data = parse_model_json(content, schema)
    except Exception:
        data = extract_labeled_values(source_text, schema)
        warnings.append("Model-assisted extraction failed; only explicit labeled values were used.")
    StructuredExtraction.objects.update_or_create(
        run=run,
        defaults={"schema": schema, "data": data, "warnings": warnings},
    )


def execute_research_run(run_id: str) -> None:
    with transaction.atomic():
        run = (
            ResearchRun.objects.select_for_update(of=("self",))
            .select_related("coworker", "coworker__current_version")
            .get(id=run_id)
        )
        if run.status in {
            ResearchRun.Status.COMPLETED,
            ResearchRun.Status.CANCELLED,
        }:
            return
        if run.started_at is None:
            run.started_at = timezone.now()
            run.save(update_fields=["started_at", "updated_at"])
    try:
        _check_cancelled(run)
        if not run.plan:
            run.status = ResearchRun.Status.PLANNING
            run.save(update_fields=["status", "updated_at"])
            run.plan = _plan_queries(run)
            run.save(update_fields=["plan", "updated_at"])
            _set_stage(run, "planning", 10, f"Planned {len(run.plan)} search queries.")

        _check_cancelled(run)
        if not run.sources.exists():
            controls = run.controls
            blocked = list(controls.get("blocked_domains", []))
            trusted = list(controls.get("trusted_domains", []))
            max_sources = min(max(int(controls.get("max_sources", 8)), 2), 20)
            use_browser = bool(controls.get("use_browser"))
            candidates: list[dict] = []
            if run.mode == ResearchRun.Mode.CRAWL or run.query.startswith(("http://", "https://")) and controls.get("crawl"):
                crawled = crawl_website(run.query, controls=controls)
                for page in crawled["pages"]:
                    CrawlPage.objects.get_or_create(
                        run=run,
                        url=str(page.get("url", "")),
                        defaults={
                            "parent_url": str(page.get("parent_url", "")),
                            "depth": int(page.get("depth", 0)),
                            "status_code": page.get("status_code"),
                            "robots_allowed": bool(page.get("robots_allowed", True)),
                            "from_cache": bool(page.get("from_cache")),
                            "checksum": str(page.get("checksum", "")),
                            "error_message": str(page.get("error", "")),
                        },
                    )
                    if page.get("text"):
                        _store_source(run, page, ResearchSource.SourceType.WEBPAGE)
            else:
                for query in run.plan[:5]:
                    try:
                        candidates.extend(search_web(query, max_results=8))
                    except WebSearchError:
                        continue
                deduped: dict[str, dict] = {}
                for candidate in candidates:
                    candidate_url = str(candidate.get("url", ""))
                    if not candidate_url or is_blocked_url(candidate_url, blocked):
                        continue
                    deduped.setdefault(candidate_url, candidate)
                ranked = sorted(
                    deduped.values(),
                    key=lambda item: not any(
                        domain_matches(urlsplit(item["url"]).hostname or "", rule)
                        for rule in trusted
                    ),
                )
                _set_stage(run, "searching", 30, f"Found {len(ranked)} candidate sources.")
                for candidate in ranked[:max_sources]:
                    _check_cancelled(run)
                    try:
                        if use_browser:
                            page = browse_webpage(
                                candidate["url"],
                                blocked_domains=blocked,
                            )
                            source_type = ResearchSource.SourceType.BROWSER
                        else:
                            page = read_public_document(
                                candidate["url"],
                                blocked_domains=blocked,
                            )
                            source_type = (
                                ResearchSource.SourceType.DOCUMENT
                                if page.get("document_type")
                                else ResearchSource.SourceType.WEBPAGE
                            )
                        for field in ("published_at", "publisher", "language"):
                            if not page.get(field) and candidate.get(field):
                                page[field] = candidate[field]
                        page["discovery_provider"] = candidate.get("provider", "")
                        page["discovery_country"] = candidate.get("country", "")
                        candidate_country = str(candidate.get("country") or "").strip()
                        if not page.get("country") and 1 < len(candidate_country) <= 3:
                            page["country"] = candidate_country
                        source = _store_source(run, page, source_type)
                        if source and any(
                            domain_matches(urlsplit(source.url).hostname or "", rule)
                            for rule in trusted
                        ):
                            source.trust_level = ResearchSource.TrustLevel.TRUSTED
                            source.save(update_fields=["trust_level"])
                    except (DocumentReadError, BrowserReadError, CrawlError):
                        continue
            _set_stage(
                run,
                "reading",
                60,
                f"Read {run.sources.filter(duplicate_of__isnull=True).count()} unique sources.",
            )

        _check_cancelled(run)
        evidence = list(
            ResearchEvidence.objects.filter(source__run=run).select_related("source")
        )
        if not evidence:
            evidence = _evidence_for_sources(run)
        conflicts = _detect_conflicts(run, evidence)
        weak_reasons = _quality(run, evidence, conflicts)
        run.conflicts = conflicts
        run.weak_evidence = bool(weak_reasons)
        run.weak_evidence_reasons = weak_reasons
        run.save(
            update_fields=[
                "conflicts",
                "weak_evidence",
                "weak_evidence_reasons",
                "updated_at",
            ]
        )
        _set_stage(run, "comparing", 75, "Compared evidence and evaluated research quality.")

        _check_cancelled(run)
        _run_extraction(run, evidence)
        report = _write_report(run, evidence, conflicts, weak_reasons)
        _bind_report_claims(report, evidence)
        run.report_markdown = report
        run.status = ResearchRun.Status.COMPLETED
        run.current_stage = "completed"
        run.progress = 100
        run.completed_at = timezone.now()
        run.error_message = ""
        run.save(
            update_fields=[
                "report_markdown",
                "status",
                "current_stage",
                "progress",
                "completed_at",
                "error_message",
                "updated_at",
            ]
        )
        _set_stage(run, "completed", 100, "Research report completed.")
        _notify_user(
            user_id=run.created_by_id,
            workspace_id=run.workspace_id,
            notification_type=Notification.Type.RESEARCH_COMPLETED,
            payload={
                "research_run_id": str(run.id),
                "title": run.query[:150],
                "status": "completed",
            },
        )
        write_audit_log(
            actor_type="user",
            actor_id=run.created_by_id,
            action="research.completed",
            resource_type="research_run",
            resource_id=run.id,
            workspace_id=run.workspace_id,
            metadata={"sources": len(evidence), "weak_evidence": bool(weak_reasons)},
        )
    except InterruptedError:
        return
    except Exception as exc:
        run.status = ResearchRun.Status.FAILED
        run.current_stage = "failed"
        run.error_message = str(exc)[:4000]
        run.completed_at = timezone.now()
        run.save(
            update_fields=[
                "status",
                "current_stage",
                "error_message",
                "completed_at",
                "updated_at",
            ]
        )
        ResearchStep.objects.create(
            run=run,
            sequence=(run.steps.aggregate(value=Max("sequence"))["value"] or 0) + 1,
            stage="failed",
            status=ResearchStep.Status.FAILED,
            message="Research failed.",
            details={"error": run.error_message},
        )
        raise


def evaluate_due_monitors() -> int:
    now = timezone.now()
    queued: list[str] = []
    with transaction.atomic():
        due = list(
            WebsiteMonitor.objects.select_for_update(skip_locked=True)
            .filter(enabled=True, next_run_at__lte=now)
            .order_by("next_run_at")[:100]
        )
        for monitor in due:
            interval = timedelta(
                days=7 if monitor.frequency == WebsiteMonitor.Frequency.WEEKLY else 1
            )
            monitor.next_run_at = max(monitor.next_run_at + interval, now + interval)
            monitor.save(update_fields=["next_run_at", "updated_at"])
            check = WebsiteMonitorRun.objects.create(monitor=monitor)
            queued.append(str(check.id))
        if queued:
            from worker.tasks import execute_website_monitor

            transaction.on_commit(
                lambda ids=queued: [execute_website_monitor.delay(value) for value in ids]
            )
    return len(queued)


def _bounded_diff(previous: str, current: str) -> tuple[str, str, bool]:
    before = [" ".join(line.split()) for line in previous.splitlines() if line.strip()][:1000]
    after = [" ".join(line.split()) for line in current.splitlines() if line.strip()][:1000]
    before_set, after_set = set(before), set(after)
    added = [line for line in after if line not in before_set][:100]
    removed = [line for line in before if line not in after_set][:100]
    total = max(len(before_set | after_set), 1)
    ratio = (len(set(added)) + len(set(removed))) / total
    meaningful = ratio >= settings.MONITOR_MEANINGFUL_CHANGE_RATIO
    diff = "\n".join(
        list(
            unified_diff(
                before[:500],
                after[:500],
                fromfile="previous",
                tofile="current",
                lineterm="",
            )
        )[: settings.MONITOR_MAX_DIFF_LINES]
    )
    summary = (
        f"{len(added)} added and {len(removed)} removed text section(s)"
        if meaningful
        else "No meaningful content change detected"
    )
    return summary, diff, meaningful


def execute_monitor_run(check_id: str, *, final_attempt: bool = True) -> None:
    with transaction.atomic():
        check = (
            WebsiteMonitorRun.objects.select_for_update()
            .select_related("monitor", "monitor__created_by")
            .get(id=check_id)
        )
        if check.status != WebsiteMonitorRun.Status.QUEUED:
            return
        check.status = WebsiteMonitorRun.Status.RUNNING
        check.started_at = timezone.now()
        check.save(update_fields=["status", "started_at"])
    monitor = check.monitor
    try:
        if monitor.use_browser:
            page = browse_webpage(
                monitor.url,
                blocked_domains=monitor.controls.get("blocked_domains", []),
            )
        elif monitor.crawl_pages > 1:
            crawl = crawl_website(
                monitor.url,
                controls={
                    **monitor.controls,
                    "max_pages": monitor.crawl_pages,
                    "max_depth": monitor.max_depth,
                },
            )
            readable = [page for page in crawl["pages"] if page.get("text")]
            page = {
                "url": monitor.url,
                "title": monitor.name,
                "text": "\n\n".join(item["text"] for item in readable),
                "pages": [
                    {"url": item["url"], "checksum": item.get("checksum", "")}
                    for item in readable
                ],
            }
        else:
            page = read_public_document(
                monitor.url,
                blocked_domains=monitor.controls.get("blocked_domains", []),
            )
        text = str(page.get("text", "")).strip()
        checksum = hashlib.sha256(" ".join(text.split()).encode()).hexdigest()
        previous = monitor.snapshots.order_by("-captured_at").first()
        summary, diff, changed = (
            _bounded_diff(previous.text, text)
            if previous is not None and previous.checksum != checksum
            else (
                "Baseline snapshot recorded" if previous is None else "No content change detected",
                "",
                False,
            )
        )
        snapshot = WebsiteSnapshot.objects.create(
            monitor=monitor,
            url=str(page.get("url") or monitor.url),
            title=str(page.get("title") or monitor.name)[:500],
            checksum=checksum,
            text=text[: settings.MONITOR_MAX_SNAPSHOT_CHARS],
            metadata={
                "published_at": page.get("published_at", ""),
                "last_modified": page.get("last_modified", ""),
                "language": page.get("language", ""),
                "pages": page.get("pages", []),
            },
        )
        check.status = WebsiteMonitorRun.Status.COMPLETED
        check.snapshot = snapshot
        check.change_detected = changed
        check.change_summary = summary
        check.diff = diff
        check.error_message = ""
        check.completed_at = timezone.now()
        check.save(
            update_fields=[
                "status",
                "snapshot",
                "change_detected",
                "change_summary",
                "diff",
                "error_message",
                "completed_at",
            ]
        )
        monitor.last_run_at = check.completed_at
        monitor.save(update_fields=["last_run_at", "updated_at"])
        retained = list(
            monitor.snapshots.order_by("-captured_at").values_list("id", flat=True)[
                settings.MONITOR_SNAPSHOT_RETENTION :
            ]
        )
        if retained:
            WebsiteSnapshot.objects.filter(id__in=retained).delete()
        if changed:
            _notify_user(
                user_id=monitor.created_by_id,
                workspace_id=monitor.workspace_id,
                notification_type=Notification.Type.WEBSITE_CHANGED,
                payload={
                    "monitor_id": str(monitor.id),
                    "snapshot_id": str(snapshot.id),
                    "title": monitor.name,
                    "url": snapshot.url,
                    "change_summary": summary,
                },
            )
    except Exception as exc:
        check.status = (
            WebsiteMonitorRun.Status.FAILED
            if final_attempt
            else WebsiteMonitorRun.Status.QUEUED
        )
        check.error_message = str(exc)[:4000]
        check.completed_at = timezone.now() if final_attempt else None
        check.save(update_fields=["status", "error_message", "completed_at"])
        if final_attempt:
            _notify_user(
                user_id=monitor.created_by_id,
                workspace_id=monitor.workspace_id,
                notification_type=Notification.Type.MONITOR_FAILED,
                payload={
                    "monitor_id": str(monitor.id),
                    "title": monitor.name,
                    "url": monitor.url,
                    "error": check.error_message,
                },
            )
        raise
