from __future__ import annotations

from rest_framework import serializers

from ai.structured_extraction import ExtractionError, validate_field_schema
from ai.web_crawler import normalize_domain
from ai.web_reader import WebPageError, validate_public_url
from research.models import (
    ResearchDomainPolicy,
    ResearchEvidence,
    ResearchRun,
    ResearchSource,
    ResearchStep,
    StructuredExtraction,
    WebsiteMonitor,
    WebsiteMonitorRun,
    WebsiteSnapshot,
)


def _validated_domains(values) -> list[str]:
    if not isinstance(values, list) or len(values) > 100:
        raise serializers.ValidationError("Domain lists must contain at most 100 entries.")
    result = []
    for value in values:
        try:
            domain = normalize_domain(str(value))
        except Exception as exc:
            raise serializers.ValidationError(str(exc)) from exc
        if domain and domain not in result:
            result.append(domain)
    return result


def validate_controls(value) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise serializers.ValidationError("Research controls must be an object.")
    allowed = {
        "max_sources",
        "minimum_sources",
        "recency_days",
        "language",
        "country",
        "trusted_domains",
        "blocked_domains",
        "use_browser",
        "crawl",
        "max_pages",
        "max_depth",
        "rate_limit_seconds",
        "max_chars_per_page",
        "extraction_schema",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise serializers.ValidationError(f"Unknown research controls: {', '.join(unknown)}.")
    result = dict(value)
    result["trusted_domains"] = _validated_domains(value.get("trusted_domains", []))
    result["blocked_domains"] = _validated_domains(value.get("blocked_domains", []))
    overlap = set(result["trusted_domains"]) & set(result["blocked_domains"])
    if overlap:
        raise serializers.ValidationError(
            f"Domains cannot be both trusted and blocked: {', '.join(sorted(overlap))}."
        )
    for field, minimum, maximum in (
        ("max_sources", 2, 20),
        ("minimum_sources", 1, 10),
        ("recency_days", 1, 3650),
        ("max_pages", 1, 50),
        ("max_depth", 0, 3),
        ("max_chars_per_page", 1000, 30000),
    ):
        if field in result and result[field] not in (None, ""):
            try:
                result[field] = int(result[field])
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError({field: "Must be an integer."}) from exc
            if result[field] < minimum or result[field] > maximum:
                raise serializers.ValidationError(
                    {field: f"Must be between {minimum} and {maximum}."}
                )
    if "rate_limit_seconds" in result:
        try:
            result["rate_limit_seconds"] = float(result["rate_limit_seconds"])
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError(
                {"rate_limit_seconds": "Must be a number."}
            ) from exc
        if not 0 <= result["rate_limit_seconds"] <= 10:
            raise serializers.ValidationError(
                {"rate_limit_seconds": "Must be between 0 and 10."}
            )
    if result.get("language"):
        result["language"] = str(result["language"]).strip().lower()[:10]
    if result.get("country"):
        result["country"] = str(result["country"]).strip().upper()[:2]
    if result.get("extraction_schema"):
        try:
            result["extraction_schema"] = validate_field_schema(
                result["extraction_schema"]
            )
        except ExtractionError as exc:
            raise serializers.ValidationError({"extraction_schema": str(exc)}) from exc
    return result


class ResearchEvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResearchEvidence
        fields = [
            "id",
            "ordinal",
            "claim",
            "passage",
            "locator",
            "page_number",
            "relevance",
        ]


class ResearchSourceSerializer(serializers.ModelSerializer):
    evidence = ResearchEvidenceSerializer(many=True, read_only=True)

    class Meta:
        model = ResearchSource
        fields = [
            "id",
            "source_type",
            "requested_url",
            "url",
            "canonical_url",
            "title",
            "publisher",
            "published_at",
            "accessed_at",
            "language",
            "country",
            "content_type",
            "checksum",
            "metadata",
            "trust_level",
            "duplicate_of_id",
            "evidence",
        ]


class ResearchStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResearchStep
        fields = ["id", "sequence", "stage", "status", "message", "details", "created_at"]


class StructuredExtractionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StructuredExtraction
        fields = ["id", "schema", "data", "warnings", "created_at"]


class ResearchRunSerializer(serializers.ModelSerializer):
    steps = ResearchStepSerializer(many=True, read_only=True)
    sources = ResearchSourceSerializer(many=True, read_only=True)
    extraction = StructuredExtractionSerializer(read_only=True)
    coworker_name = serializers.CharField(source="coworker.name", read_only=True)

    class Meta:
        model = ResearchRun
        fields = [
            "id",
            "workspace_id",
            "created_by_id",
            "coworker_id",
            "coworker_name",
            "query",
            "mode",
            "status",
            "current_stage",
            "progress",
            "controls",
            "plan",
            "report_markdown",
            "weak_evidence",
            "weak_evidence_reasons",
            "conflicts",
            "error_message",
            "cancel_requested",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
            "steps",
            "sources",
            "extraction",
        ]


class ResearchRunSummarySerializer(serializers.ModelSerializer):
    source_count = serializers.IntegerField(read_only=True)
    coworker_name = serializers.CharField(source="coworker.name", read_only=True)

    class Meta:
        model = ResearchRun
        fields = [
            "id",
            "workspace_id",
            "coworker_id",
            "coworker_name",
            "query",
            "mode",
            "status",
            "current_stage",
            "progress",
            "weak_evidence",
            "error_message",
            "created_at",
            "updated_at",
            "completed_at",
            "source_count",
        ]


class ResearchRunCreateSerializer(serializers.Serializer):
    workspace_id = serializers.UUIDField()
    coworker_id = serializers.UUIDField(required=False, allow_null=True)
    query = serializers.CharField(max_length=4000)
    mode = serializers.ChoiceField(
        choices=ResearchRun.Mode.choices, default=ResearchRun.Mode.DEEP
    )
    controls = serializers.JSONField(required=False, default=dict)

    def validate_controls(self, value):
        return validate_controls(value)

    def validate(self, attrs):
        query = attrs["query"].strip()
        attrs["query"] = query
        if attrs["mode"] == ResearchRun.Mode.CRAWL or attrs["controls"].get("crawl"):
            try:
                attrs["query"] = validate_public_url(query)
            except WebPageError as exc:
                raise serializers.ValidationError({"query": str(exc)}) from exc
        return attrs


class WebsiteSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebsiteSnapshot
        fields = ["id", "url", "title", "checksum", "metadata", "captured_at"]


class WebsiteMonitorRunSerializer(serializers.ModelSerializer):
    snapshot = WebsiteSnapshotSerializer(read_only=True)

    class Meta:
        model = WebsiteMonitorRun
        fields = [
            "id",
            "status",
            "snapshot",
            "change_detected",
            "change_summary",
            "diff",
            "error_message",
            "created_at",
            "started_at",
            "completed_at",
        ]


class WebsiteMonitorSerializer(serializers.ModelSerializer):
    latest_run = serializers.SerializerMethodField()

    class Meta:
        model = WebsiteMonitor
        fields = [
            "id",
            "workspace_id",
            "created_by_id",
            "coworker_id",
            "name",
            "url",
            "frequency",
            "enabled",
            "use_browser",
            "crawl_pages",
            "max_depth",
            "controls",
            "next_run_at",
            "last_run_at",
            "created_at",
            "updated_at",
            "latest_run",
        ]

    def get_latest_run(self, obj):
        row = obj.runs.first()
        return WebsiteMonitorRunSerializer(row).data if row else None


class WebsiteMonitorCreateSerializer(serializers.Serializer):
    workspace_id = serializers.UUIDField()
    coworker_id = serializers.UUIDField(required=False, allow_null=True)
    name = serializers.CharField(max_length=255)
    url = serializers.CharField(max_length=2048)
    frequency = serializers.ChoiceField(
        choices=WebsiteMonitor.Frequency.choices,
        default=WebsiteMonitor.Frequency.DAILY,
    )
    enabled = serializers.BooleanField(default=True)
    use_browser = serializers.BooleanField(default=False)
    crawl_pages = serializers.IntegerField(min_value=1, max_value=50, default=1)
    max_depth = serializers.IntegerField(min_value=0, max_value=3, default=0)
    controls = serializers.JSONField(required=False, default=dict)

    def validate_url(self, value):
        try:
            return validate_public_url(value)
        except WebPageError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_controls(self, value):
        return validate_controls(value)


class ResearchDomainPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = ResearchDomainPolicy
        fields = ["workspace_id", "trusted_domains", "blocked_domains", "default_controls", "updated_at"]
        read_only_fields = ["workspace_id", "updated_at"]

    def validate_trusted_domains(self, value):
        return _validated_domains(value)

    def validate_blocked_domains(self, value):
        return _validated_domains(value)

    def validate_default_controls(self, value):
        return validate_controls(value)

    def validate(self, attrs):
        trusted = set(attrs.get("trusted_domains", getattr(self.instance, "trusted_domains", [])))
        blocked = set(attrs.get("blocked_domains", getattr(self.instance, "blocked_domains", [])))
        if trusted & blocked:
            raise serializers.ValidationError("A domain cannot be both trusted and blocked.")
        return attrs
