from django.db import models

from ai.models import Message
from core.models import Coworker, User, UUIDPrimaryKeyModel, Workspace


class ResearchRun(UUIDPrimaryKeyModel):
    class Mode(models.TextChoices):
        DEEP = "deep", "Deep research"
        CRAWL = "crawl", "Website crawl"
        EXTRACTION = "extraction", "Structured extraction"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PLANNING = "planning", "Planning"
        SEARCHING = "searching", "Searching"
        READING = "reading", "Reading"
        COMPARING = "comparing", "Comparing"
        WRITING = "writing", "Writing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="research_runs"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="research_runs"
    )
    coworker = models.ForeignKey(
        Coworker, on_delete=models.SET_NULL, null=True, blank=True, related_name="research_runs"
    )
    query = models.TextField()
    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.DEEP)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    current_stage = models.CharField(max_length=50, default="queued")
    progress = models.PositiveSmallIntegerField(default=0)
    controls = models.JSONField(default=dict, blank=True)
    plan = models.JSONField(default=list, blank=True)
    report_markdown = models.TextField(blank=True)
    weak_evidence = models.BooleanField(default=False)
    weak_evidence_reasons = models.JSONField(default=list, blank=True)
    conflicts = models.JSONField(default=list, blank=True)
    error_message = models.TextField(blank=True)
    cancel_requested = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "research_runs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace", "status", "created_at"]),
        ]


class ResearchStep(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    run = models.ForeignKey(ResearchRun, on_delete=models.CASCADE, related_name="steps")
    sequence = models.PositiveIntegerField()
    stage = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=Status.choices)
    message = models.CharField(max_length=500)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "research_steps"
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(fields=["run", "sequence"], name="uniq_research_step_sequence")
        ]


class ResearchSource(UUIDPrimaryKeyModel):
    class SourceType(models.TextChoices):
        WEBPAGE = "webpage", "Webpage"
        DOCUMENT = "document", "Document"
        BROWSER = "browser", "JavaScript webpage"
        SEARCH = "search", "Search result"

    class TrustLevel(models.TextChoices):
        TRUSTED = "trusted", "Trusted"
        STANDARD = "standard", "Standard"
        BLOCKED = "blocked", "Blocked"

    run = models.ForeignKey(
        ResearchRun, on_delete=models.CASCADE, null=True, blank=True, related_name="sources"
    )
    source_type = models.CharField(
        max_length=20, choices=SourceType.choices, default=SourceType.WEBPAGE
    )
    requested_url = models.TextField()
    url = models.TextField()
    canonical_url = models.TextField(blank=True)
    title = models.CharField(max_length=500, blank=True)
    publisher = models.CharField(max_length=255, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    accessed_at = models.DateTimeField(auto_now_add=True)
    language = models.CharField(max_length=30, blank=True)
    country = models.CharField(max_length=10, blank=True)
    content_type = models.CharField(max_length=255, blank=True)
    checksum = models.CharField(max_length=64)
    text = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    trust_level = models.CharField(
        max_length=20, choices=TrustLevel.choices, default=TrustLevel.STANDARD
    )
    duplicate_of = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="duplicates"
    )

    class Meta:
        db_table = "research_sources"
        ordering = ["accessed_at"]
        indexes = [
            models.Index(fields=["run", "checksum"]),
        ]


class ResearchEvidence(UUIDPrimaryKeyModel):
    source = models.ForeignKey(
        ResearchSource, on_delete=models.CASCADE, related_name="evidence"
    )
    ordinal = models.PositiveIntegerField()
    claim = models.TextField(blank=True)
    passage = models.TextField()
    locator = models.CharField(max_length=255, blank=True)
    page_number = models.PositiveIntegerField(null=True, blank=True)
    relevance = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "research_evidence"
        ordering = ["ordinal"]
        constraints = [
            models.UniqueConstraint(fields=["source", "ordinal"], name="uniq_source_evidence_ordinal")
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.passage and self.passage not in self.source.text:
            raise ValidationError({"passage": "Evidence passage must exist in the stored source."})


class MessageCitation(UUIDPrimaryKeyModel):
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name="citations"
    )
    evidence = models.ForeignKey(
        ResearchEvidence, on_delete=models.PROTECT, related_name="message_citations"
    )
    ordinal = models.PositiveIntegerField()
    claim = models.TextField(blank=True)

    class Meta:
        db_table = "message_citations"
        ordering = ["ordinal"]
        constraints = [
            models.UniqueConstraint(fields=["message", "ordinal"], name="uniq_message_citation_ordinal")
        ]


class CrawlPage(UUIDPrimaryKeyModel):
    run = models.ForeignKey(ResearchRun, on_delete=models.CASCADE, related_name="crawl_pages")
    url = models.TextField()
    parent_url = models.TextField(blank=True)
    depth = models.PositiveSmallIntegerField(default=0)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    robots_allowed = models.BooleanField(default=True)
    from_cache = models.BooleanField(default=False)
    checksum = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "crawl_pages"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["run", "url"], name="uniq_research_crawl_url")
        ]


class StructuredExtraction(UUIDPrimaryKeyModel):
    run = models.OneToOneField(
        ResearchRun, on_delete=models.CASCADE, related_name="extraction"
    )
    schema = models.JSONField()
    data = models.JSONField(default=dict)
    warnings = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "structured_extractions"


class WebsiteMonitor(UUIDPrimaryKeyModel):
    class Frequency(models.TextChoices):
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"

    workspace = models.ForeignKey(
        Workspace, on_delete=models.CASCADE, related_name="website_monitors"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="website_monitors"
    )
    coworker = models.ForeignKey(
        Coworker, on_delete=models.SET_NULL, null=True, blank=True, related_name="website_monitors"
    )
    name = models.CharField(max_length=255)
    url = models.TextField()
    frequency = models.CharField(
        max_length=20, choices=Frequency.choices, default=Frequency.DAILY
    )
    enabled = models.BooleanField(default=True)
    use_browser = models.BooleanField(default=False)
    crawl_pages = models.PositiveSmallIntegerField(default=1)
    max_depth = models.PositiveSmallIntegerField(default=0)
    controls = models.JSONField(default=dict, blank=True)
    next_run_at = models.DateTimeField()
    last_run_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "website_monitors"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["enabled", "next_run_at"]),
            models.Index(fields=["workspace", "created_at"]),
        ]


class WebsiteSnapshot(UUIDPrimaryKeyModel):
    monitor = models.ForeignKey(
        WebsiteMonitor, on_delete=models.CASCADE, related_name="snapshots"
    )
    url = models.TextField()
    title = models.CharField(max_length=500, blank=True)
    checksum = models.CharField(max_length=64)
    text = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "website_snapshots"
        ordering = ["-captured_at"]
        indexes = [models.Index(fields=["monitor", "captured_at"])]


class WebsiteMonitorRun(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    monitor = models.ForeignKey(
        WebsiteMonitor, on_delete=models.CASCADE, related_name="runs"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    snapshot = models.ForeignKey(
        WebsiteSnapshot, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    change_detected = models.BooleanField(default=False)
    change_summary = models.TextField(blank=True)
    diff = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "website_monitor_runs"
        ordering = ["-created_at"]


class ResearchDomainPolicy(UUIDPrimaryKeyModel):
    workspace = models.OneToOneField(
        Workspace, on_delete=models.CASCADE, related_name="research_domain_policy"
    )
    trusted_domains = models.JSONField(default=list, blank=True)
    blocked_domains = models.JSONField(default=list, blank=True)
    default_controls = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "research_domain_policies"
