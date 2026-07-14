"""Phase 3 enterprise governance, marketplace economy, and portability services."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from core.coworkers import create_coworker
from core.interface import write_audit_log
from core.models import (
    Artifact, AuditAnomaly, AuditLog, ComplianceExport, Coworker,
    CoworkerSkillAttachment, EnterpriseSettings, MarketplaceInstall,
    MarketplaceListingVersion, MarketplaceOrder, MarketplacePayout,
    MarketplaceSecurityReview, OrganizationPolicyRule, PermissionProfile,
    SCIMToken, Tool, CoworkerToolAttachment, User, Workflow, Workspace, WorkspaceMember,
)


ROLE_CAPABILITIES = {
    WorkspaceMember.Role.OWNER: {"*"},
    WorkspaceMember.Role.ADMIN: {"*"},
    WorkspaceMember.Role.SECURITY_ADMIN: {"security.manage", "audit.read", "compliance.export"},
    WorkspaceMember.Role.BILLING_ADMIN: {"billing.manage", "marketplace.payouts"},
    WorkspaceMember.Role.DEVELOPER_ADMIN: {"sdk.manage", "marketplace.publish", "integrations.manage"},
    WorkspaceMember.Role.AUDITOR: {"audit.read", "compliance.export"},
    WorkspaceMember.Role.MEMBER: set(),
    WorkspaceMember.Role.GUEST: set(),
}


def require_capability(user: User, workspace: Workspace, capability: str) -> WorkspaceMember:
    member = WorkspaceMember.objects.filter(workspace=workspace, user=user).first()
    if member is None:
        raise PermissionDenied("You are not a member of this workspace.")
    allowed = ROLE_CAPABILITIES.get(member.role, set())
    if "*" not in allowed and capability not in allowed:
        raise PermissionDenied(f"The {capability} capability is required.")
    return member


def evaluate_policy(
    workspace: Workspace, *, resource_type: str, action: str, context: dict[str, Any]
) -> str:
    """Evaluate first matching rule; deny is the fail-closed default for explicit rules."""
    rules = workspace.policy_rules.filter(enabled=True, resource_type__in=[resource_type, "*"]).filter(
        action__in=[action, "*"]
    )
    for rule in rules:
        if all(context.get(key) == value for key, value in rule.conditions.items()):
            return rule.effect
    return "allow"


def create_scim_token(workspace: Workspace, user: User, name: str) -> tuple[SCIMToken, str]:
    require_capability(user, workspace, "security.manage")
    plaintext = "scm_" + secrets.token_urlsafe(32)
    row = SCIMToken.objects.create(
        workspace=workspace, name=name, token_prefix=plaintext[:12],
        token_hash=hashlib.sha256(plaintext.encode()).hexdigest(), created_by=user,
    )
    return row, plaintext


def scan_listing_version(version: MarketplaceListingVersion) -> MarketplaceSecurityReview:
    manifest = version.manifest
    findings: list[dict[str, str]] = []
    score = 100
    declared = manifest.get("declared_tools", [])
    if manifest.get("bundled_code"):
        score -= 45; findings.append({"severity": "high", "code": "bundled_code", "message": "Bundled executable code requires manual review."})
    if len(declared) > 8:
        score -= 15; findings.append({"severity": "medium", "code": "broad_permissions", "message": "The package declares an unusually broad tool set."})
    dependencies = manifest.get("dependencies", [])
    if len(dependencies) > 10:
        score -= 10; findings.append({"severity": "medium", "code": "dependency_depth", "message": "The dependency set is unusually large."})
    for dependency in dependencies:
        listing_id = dependency.get("listing_id") if isinstance(dependency, dict) else dependency
        if not MarketplaceListingVersion.objects.filter(listing_id=listing_id, review_status="approved").exists():
            score -= 25; findings.append({"severity": "high", "code": "missing_dependency", "message": f"No approved version exists for dependency {listing_id}."})
    score = max(0, score)
    status = "passed" if score >= 80 else "needs_review" if score >= 50 else "failed"
    return MarketplaceSecurityReview.objects.update_or_create(
        listing_version=version, defaults={"score": score, "status": status, "findings": findings}
    )[0]


def install_dependencies(
    version: MarketplaceListingVersion, *, workspace: Workspace, user: User,
    visited: set[str] | None = None,
) -> list[MarketplaceInstall]:
    from core.v2_services import install_listing

    visited = visited or set()
    key = str(version.id)
    if key in visited:
        raise ValidationError("Marketplace dependency cycle detected.")
    visited.add(key)
    installed: list[MarketplaceInstall] = []
    for dependency in version.manifest.get("dependencies", []):
        listing_id = dependency.get("listing_id") if isinstance(dependency, dict) else dependency
        requested_version = dependency.get("version") if isinstance(dependency, dict) else None
        rows = MarketplaceListingVersion.objects.filter(listing_id=listing_id, review_status="approved")
        if requested_version:
            rows = rows.filter(version_string=requested_version)
        dependency_version = rows.order_by("-published_at").first()
        if dependency_version is None:
            raise ValidationError(f"Approved dependency {listing_id} is unavailable.")
        installed.extend(install_dependencies(dependency_version, workspace=workspace, user=user, visited=visited))
        installed.append(install_listing(dependency_version, workspace=workspace, user=user))
    return installed


def complete_marketplace_order(order: MarketplaceOrder, provider_reference: str) -> MarketplaceOrder:
    if order.status == MarketplaceOrder.Status.PAID:
        return order
    with transaction.atomic():
        order.status = MarketplaceOrder.Status.PAID
        order.provider_reference = provider_reference
        order.paid_at = timezone.now()
        order.save(update_fields=["status", "provider_reference", "paid_at"])
        gross = order.amount_usd
        fee = (gross * Decimal("0.15")).quantize(Decimal("0.01"))
        MarketplacePayout.objects.create(
            publisher_workspace=order.listing_version.listing.publisher_workspace,
            listing=order.listing_version.listing, order=order, gross_usd=gross,
            platform_fee_usd=fee, net_payout_usd=gross - fee,
        )
    return order


def export_coworker_bundle(coworker: Coworker, user: User) -> Artifact:
    workflow_templates = []
    for workflow in Workflow.objects.filter(workspace=coworker.workspace).select_related("current_version"):
        canonical = json.dumps(workflow.current_version.definition)
        if str(coworker.id) in canonical:
            workflow_templates.append({
                "name": workflow.name,
                "definition": json.loads(canonical.replace(str(coworker.id), "$coworker")),
            })
    content = {
        "schema_version": "1", "kind": "deep_foundry_coworker_bundle",
        "coworker": {
            "name": coworker.name, "avatar_url": coworker.avatar_url,
            "role_description": coworker.current_version.role_description,
            "model_binding": coworker.current_version.model_binding,
            "tools": list(coworker.tool_attachments.filter(enabled=True).values_list("tool__name", flat=True)),
            "skills": [
                {"listing_id": str(row.skill.listing_version.listing_id), "version": row.skill.listing_version.version_string}
                for row in coworker.skill_attachments.filter(enabled=True).select_related("skill__listing_version")
            ],
        },
        "workflow_templates": workflow_templates,
        "privacy": {"memory_included": False, "credentials_included": False},
    }
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return Artifact.objects.create(
        workspace=coworker.workspace, artifact_type=Artifact.ArtifactType.COWORKER_BUNDLE,
        name=f"{coworker.name} bundle", content=content,
        checksum=hashlib.sha256(canonical.encode()).hexdigest(), created_by=user,
        source_coworker=coworker,
    )


def import_coworker_bundle(workspace: Workspace, user: User, content: dict[str, Any]) -> Coworker:
    if content.get("kind") not in {
        "deep_foundry_coworker_bundle",
        "agentarium_coworker_bundle",
    } or content.get("schema_version") != "1":
        raise ValidationError("Unsupported coworker bundle format.")
    data = content.get("coworker") or {}
    profile, _ = PermissionProfile.objects.get_or_create(workspace=workspace, name="Default")
    coworker = create_coworker(
        workspace=workspace, owner=user, created_by=user, name=data.get("name", "Imported coworker"),
        avatar_url=data.get("avatar_url"), role_description=data.get("role_description", ""),
        model_binding=data.get("model_binding", {"primary": "deepseek-v4-flash"}),
        permission_profile=profile,
    )
    for tool in Tool.objects.filter(name__in=data.get("tools", [])):
        CoworkerToolAttachment.objects.get_or_create(coworker=coworker, tool=tool)
    for skill_ref in data.get("skills", []):
        install = MarketplaceInstall.objects.filter(
            workspace=workspace,
            listing_version__listing_id=skill_ref.get("listing_id"),
            listing_version__version_string=skill_ref.get("version"),
        ).select_related("listing_version__skill").first()
        if install and hasattr(install.listing_version, "skill"):
            CoworkerSkillAttachment.objects.get_or_create(
                coworker=coworker, skill=install.listing_version.skill
            )
    from core.v2_services import create_workflow

    for template in content.get("workflow_templates", []):
        canonical = json.dumps(template.get("definition", {})).replace("$coworker", str(coworker.id))
        create_workflow(
            workspace=workspace, user=user,
            name=f"{template.get('name', coworker.name)} (imported)",
            definition=json.loads(canonical),
        )
    return coworker


def build_compliance_export(
    workspace: Workspace, user: User, export_type: str, period_start=None, period_end=None
) -> ComplianceExport:
    require_capability(user, workspace, "compliance.export")
    audit_rows = AuditLog.objects.filter(workspace=workspace)
    if period_start: audit_rows = audit_rows.filter(created_at__gte=period_start)
    if period_end: audit_rows = audit_rows.filter(created_at__lte=period_end)
    evidence = {
        "workspace": {"id": str(workspace.id), "name": workspace.name},
        "generated_at": timezone.now().isoformat(),
        "access_review": list(workspace.members.values("user__email", "role", "joined_at")),
        "policy_floors": list(workspace.policy_floors.values("tool_risk_classification", "min_required_policy", "enforced")),
        "policy_rules": list(workspace.policy_rules.values("name", "resource_type", "action", "effect", "enabled")),
        "audit_log": list(audit_rows.order_by("created_at").values("actor_type", "actor_id", "action", "resource_type", "resource_id", "metadata", "created_at")),
        "open_anomalies": list(workspace.audit_anomalies.filter(status="open").values("severity", "summary", "detected_at")),
    }
    evidence = json.loads(json.dumps(evidence, default=str))
    canonical = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    return ComplianceExport.objects.create(
        workspace=workspace, export_type=export_type, requested_by=user,
        period_start=period_start, period_end=period_end, evidence=evidence,
        checksum=hashlib.sha256(canonical.encode()).hexdigest(),
    )


def detect_audit_anomalies(workspace: Workspace) -> list[AuditAnomaly]:
    since = timezone.now() - timedelta(minutes=15)
    recent = AuditLog.objects.filter(workspace=workspace, created_at__gte=since)
    created: list[AuditAnomaly] = []
    dangerous_count = recent.filter(action__icontains="approved", metadata__risk_classification="dangerous").count()
    if dangerous_count >= 5 and not workspace.audit_anomalies.filter(anomaly_type="dangerous_tool_spike", detected_at__gte=since).exists():
        created.append(AuditAnomaly.objects.create(
            workspace=workspace, anomaly_type="dangerous_tool_spike", severity="high",
            summary=f"{dangerous_count} dangerous actions were approved in 15 minutes.",
            evidence={"count": dangerous_count, "window_minutes": 15},
        ))
    actor_counts = recent.exclude(actor_id=None).values("actor_id").annotate(total=Count("id")).filter(total__gte=50)
    for row in actor_counts:
        if not workspace.audit_anomalies.filter(anomaly_type="activity_spike", evidence__actor_id=str(row["actor_id"]), detected_at__gte=since).exists():
            created.append(AuditAnomaly.objects.create(
                workspace=workspace, anomaly_type="activity_spike", severity="medium",
                summary="An actor generated unusually high activity.",
                evidence={"actor_id": str(row["actor_id"]), "count": row["total"], "window_minutes": 15},
            ))
    return created
