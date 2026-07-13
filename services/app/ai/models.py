"""
AI-module models — Milestone 2 scope: model_calls only, per DATABASE.md §3.4.

`ai` is a distinct Django app (not merged into `core`) specifically so the
`core`/`ai` "logical schema" boundary from DATABASE.md §1 has a real
enforcement mechanism (separate model registries, separate migration
histories) rather than being just a naming convention — consistent with
ARCHITECTURE.md ADR-006 treating the Core/AI split as a code-organization
seam even though both run in one process.
"""

from django.db import models

from core.models import ProviderCredential, UUIDPrimaryKeyModel, Workspace


class ModelCall(UUIDPrimaryKeyModel):
    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        ERROR = "error", "Error"
        RATE_LIMITED = "rate_limited", "Rate limited"

    request_id = models.UUIDField()
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="model_calls")
    # No Coworker FK yet — that model doesn't exist until Milestone 3.
    coworker_id = models.UUIDField(null=True, blank=True)
    deployment_mode = models.CharField(
        max_length=30, choices=ProviderCredential.DeploymentMode.choices
    )
    model_id = models.CharField(max_length=100)
    capability_requested = models.JSONField(default=dict, blank=True)
    fallback_used = models.BooleanField(default=False)
    input_tokens = models.IntegerField(null=True, blank=True)
    output_tokens = models.IntegerField(null=True, blank=True)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    latency_ms = models.IntegerField()
    status = models.CharField(max_length=20, choices=Status.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "model_calls"

    def __str__(self) -> str:
        return f"{self.model_id} ({self.status}) @ {self.created_at}"
