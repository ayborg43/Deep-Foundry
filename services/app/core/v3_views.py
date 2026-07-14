from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import urllib.parse
import urllib.request
from decimal import Decimal

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.encryption import decrypt_from_bytes, encrypt_to_bytes
from core.interface import write_audit_log
from core.models import (
    Artifact, AuditAnomaly, ComplianceExport, Coworker, EnterpriseSettings,
    MarketplaceInstall, MarketplaceListingVersion, MarketplaceOrder,
    MarketplacePayout, OrganizationPolicyRule, PayoutAccount, SCIMToken,
    SSOProvider, User, Workspace, WorkspaceMember,
)
from core.permissions import get_coworker_for_member, get_workspace_for_member
from core.provisioning import provision_personal_workspace
from core.scim_auth import SCIMTokenAuthentication
from core.v2_services import install_listing
from core.v3_services import (
    build_compliance_export, complete_marketplace_order, create_scim_token,
    detect_audit_anomalies, evaluate_policy, export_coworker_bundle,
    import_coworker_bundle, install_dependencies, require_capability,
)


def _enterprise(workspace: Workspace) -> EnterpriseSettings:
    return EnterpriseSettings.objects.get_or_create(workspace=workspace)[0]


class EnterpriseSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id)
        row = _enterprise(workspace)
        return Response({"data_region": row.data_region, "retention_days": row.retention_days, "legal_hold": row.legal_hold, "support_tier": row.support_tier, "sla_uptime_percent": str(row.sla_uptime_percent), "sla_response_minutes": row.sla_response_minutes})

    def patch(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id)
        require_capability(request.user, workspace, "security.manage")
        row = _enterprise(workspace)
        region = request.data.get("data_region", row.data_region)
        if region not in EnterpriseSettings.DataRegion.values:
            raise ValidationError({"data_region": "Unsupported data region."})
        if row.data_region != region and (workspace.tasks.exists() or workspace.audit_logs.exists()):
            raise ValidationError({"data_region": "Export and migrate existing data before changing regions."})
        retention = int(request.data.get("retention_days", row.retention_days))
        if not 1 <= retention <= 3650:
            raise ValidationError({"retention_days": "Retention must be between 1 and 3650 days."})
        for field in ("legal_hold", "support_tier", "sla_uptime_percent", "sla_response_minutes"):
            if field in request.data: setattr(row, field, request.data[field])
        row.data_region = region; row.retention_days = retention; row.save()
        return self.get(request, workspace_id)


class PolicyRuleListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id)
        require_capability(request.user, workspace, "audit.read")
        return Response([{"id": str(r.id), "name": r.name, "resource_type": r.resource_type, "action": r.action, "conditions": r.conditions, "effect": r.effect, "priority": r.priority, "enabled": r.enabled} for r in workspace.policy_rules.all()])

    def post(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id)
        require_capability(request.user, workspace, "security.manage")
        effect = request.data.get("effect")
        if effect not in OrganizationPolicyRule.Effect.values:
            raise ValidationError({"effect": "Unsupported policy effect."})
        row = OrganizationPolicyRule.objects.create(
            workspace=workspace, name=request.data.get("name", "Policy rule"),
            resource_type=request.data.get("resource_type", "*"), action=request.data.get("action", "*"),
            conditions=request.data.get("conditions", {}), effect=effect,
            priority=request.data.get("priority", 100), enabled=request.data.get("enabled", True),
        )
        return Response({"id": str(row.id), "name": row.name, "effect": row.effect}, status=201)


class PolicyRuleDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, workspace_id, rule_id):
        workspace = get_workspace_for_member(request.user, workspace_id)
        require_capability(request.user, workspace, "security.manage")
        get_object_or_404(OrganizationPolicyRule, workspace=workspace, id=rule_id).delete()
        return Response(status=204)


class SSOProviderListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id)
        require_capability(request.user, workspace, "security.manage")
        return Response([{"id": str(p.id), "name": p.name, "protocol": p.protocol, "issuer": p.issuer, "sso_url": p.sso_url, "entity_id": p.entity_id, "client_id": p.client_id, "email_domains": p.email_domains, "jit_provisioning": p.jit_provisioning, "enforce_sso": p.enforce_sso, "enabled": p.enabled} for p in workspace.sso_providers.all()])

    def post(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id)
        require_capability(request.user, workspace, "security.manage")
        protocol = request.data.get("protocol")
        if protocol not in SSOProvider.Protocol.values:
            raise ValidationError({"protocol": "Use saml or oidc."})
        row = SSOProvider.objects.create(
            workspace=workspace, name=request.data.get("name", "Enterprise SSO"), protocol=protocol,
            issuer=request.data.get("issuer", ""), sso_url=request.data.get("sso_url", ""),
            entity_id=request.data.get("entity_id", ""), client_id=request.data.get("client_id", ""),
            encrypted_secret=encrypt_to_bytes(request.data.get("secret", "")) if request.data.get("secret") else None,
            email_domains=request.data.get("email_domains", []), attribute_mapping=request.data.get("attribute_mapping", {}),
            jit_provisioning=request.data.get("jit_provisioning", True), enforce_sso=request.data.get("enforce_sso", False),
        )
        return Response({"id": str(row.id), "protocol": row.protocol}, status=201)


class SSOLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, provider_id):
        provider = get_object_or_404(SSOProvider, id=provider_id, enabled=True)
        state = signing.dumps({"provider_id": str(provider.id), "nonce": secrets.token_urlsafe(16)}, salt="enterprise-sso")
        callback = request.build_absolute_uri(f"/api/v1/sso/{provider.id}/callback")
        if provider.protocol == SSOProvider.Protocol.OIDC:
            query = urllib.parse.urlencode({"client_id": provider.client_id, "response_type": "code", "scope": "openid email profile", "redirect_uri": callback, "state": state})
            return Response({"authorization_url": f"{provider.sso_url}?{query}", "state": state})
        return Response({"sso_url": provider.sso_url, "entity_id": provider.entity_id, "relay_state": state, "acs_url": callback})


def _provision_sso_user(provider: SSOProvider, email: str, display_name: str):
    domain = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
    if provider.email_domains and domain not in [item.lower() for item in provider.email_domains]:
        raise PermissionDenied("The identity email domain is not allowed for this provider.")
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        if not provider.jit_provisioning: raise PermissionDenied("JIT provisioning is disabled.")
        user = User.objects.create(email=User.objects.normalize_email(email), display_name=display_name)
        user.set_unusable_password(); user.save(update_fields=["password"])
    WorkspaceMember.objects.get_or_create(workspace=provider.workspace, user=user, defaults={"role": WorkspaceMember.Role.MEMBER})
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(user)
    return user, {"access": str(refresh.access_token), "refresh": str(refresh)}


class SSOCallbackView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, provider_id):
        provider = get_object_or_404(SSOProvider, id=provider_id, enabled=True)
        state = request.data.get("state") or request.data.get("RelayState")
        try: payload = signing.loads(state, salt="enterprise-sso", max_age=600)
        except signing.BadSignature as exc: raise ValidationError("Invalid or expired SSO state.") from exc
        if payload.get("provider_id") != str(provider.id): raise ValidationError("SSO provider mismatch.")
        if provider.protocol == SSOProvider.Protocol.SAML:
            assertion = request.data.get("assertion") or {}
            signature = request.data.get("signature", "")
            secret = decrypt_from_bytes(bytes(provider.encrypted_secret)) if provider.encrypted_secret else ""
            canonical = json.dumps(assertion, sort_keys=True, separators=(",", ":"))
            expected = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
            if not secret or not hmac.compare_digest(signature, expected): raise PermissionDenied("Invalid SAML broker signature.")
            if assertion.get("issuer") != provider.issuer or assertion.get("audience") != provider.entity_id: raise PermissionDenied("SAML issuer or audience mismatch.")
            email, name = assertion.get("email", ""), assertion.get("display_name", "")
        else:
            code = request.data.get("code")
            endpoints = provider.attribute_mapping
            if not code or not endpoints.get("token_endpoint") or not endpoints.get("userinfo_endpoint"): raise ValidationError("OIDC code and discovery endpoints are required.")
            secret = decrypt_from_bytes(bytes(provider.encrypted_secret)) if provider.encrypted_secret else ""
            token_request = urllib.request.Request(endpoints["token_endpoint"], data=urllib.parse.urlencode({"grant_type": "authorization_code", "code": code, "client_id": provider.client_id, "client_secret": secret, "redirect_uri": request.build_absolute_uri()}).encode(), method="POST")
            with urllib.request.urlopen(token_request, timeout=15) as response: token_data = json.load(response)
            info_request = urllib.request.Request(endpoints["userinfo_endpoint"], headers={"Authorization": f"Bearer {token_data['access_token']}"})
            with urllib.request.urlopen(info_request, timeout=15) as response: claims = json.load(response)
            email, name = claims.get("email", ""), claims.get("name", "")
        if not email: raise ValidationError("The identity provider did not supply an email address.")
        user, tokens = _provision_sso_user(provider, email, name)
        write_audit_log(actor_type="user", actor_id=user.id, action="sso.login", resource_type="workspace", resource_id=provider.workspace_id, workspace_id=provider.workspace_id, metadata={"provider_id": str(provider.id), "protocol": provider.protocol})
        return Response({"user": {"id": str(user.id), "email": user.email, "display_name": user.display_name}, "workspace_id": str(provider.workspace_id), "tokens": tokens})


class SCIMTokenListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id); require_capability(request.user, workspace, "security.manage")
        return Response([{"id": str(t.id), "name": t.name, "prefix": t.token_prefix, "last_used_at": t.last_used_at, "revoked_at": t.revoked_at} for t in workspace.scim_tokens.all()])

    def post(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id)
        row, token = create_scim_token(workspace, request.user, request.data.get("name", "Directory sync"))
        return Response({"id": str(row.id), "token": token, "prefix": row.token_prefix}, status=201)


class SCIMUsersView(APIView):
    authentication_classes = [SCIMTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        members = request.auth.workspace.members.select_related("user")
        resources = [{"id": str(m.user_id), "userName": m.user.email, "active": m.user.is_active, "displayName": m.user.display_name or "", "roles": [{"value": m.role}]} for m in members]
        return Response({"schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"], "totalResults": len(resources), "Resources": resources, "startIndex": 1, "itemsPerPage": len(resources)})

    def post(self, request):
        email = User.objects.normalize_email(request.data.get("userName", ""))
        if not email: raise ValidationError({"userName": "Email is required."})
        user, created = User.objects.get_or_create(email=email, defaults={"display_name": request.data.get("displayName", "")})
        if created: user.set_unusable_password(); user.save(update_fields=["password"])
        role = ((request.data.get("roles") or [{}])[0].get("value") or WorkspaceMember.Role.MEMBER)
        if role not in WorkspaceMember.Role.values: role = WorkspaceMember.Role.MEMBER
        WorkspaceMember.objects.update_or_create(workspace=request.auth.workspace, user=user, defaults={"role": role})
        return Response({"id": str(user.id), "userName": user.email, "active": user.is_active, "displayName": user.display_name or ""}, status=201)


class SCIMUserDetailView(APIView):
    authentication_classes = [SCIMTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, user_id):
        member = get_object_or_404(WorkspaceMember, workspace=request.auth.workspace, user_id=user_id)
        for operation in request.data.get("Operations", []):
            path, value = operation.get("path", "").lower(), operation.get("value")
            if path == "active": member.user.is_active = bool(value); member.user.save(update_fields=["is_active"])
            elif path in ("roles", "role"):
                role = value[0].get("value") if isinstance(value, list) else value
                if role in WorkspaceMember.Role.values: member.role = role; member.save(update_fields=["role"])
        return Response({"id": str(member.user_id), "userName": member.user.email, "active": member.user.is_active, "roles": [{"value": member.role}]})

    def delete(self, request, user_id):
        member = get_object_or_404(WorkspaceMember, workspace=request.auth.workspace, user_id=user_id)
        if member.role == WorkspaceMember.Role.OWNER: raise ValidationError("The workspace owner cannot be deprovisioned.")
        member.user.is_active = False; member.user.save(update_fields=["is_active"]); member.delete()
        return Response(status=204)


class AuditAnomalyListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id); require_capability(request.user, workspace, "audit.read")
        if request.query_params.get("scan") == "true": detect_audit_anomalies(workspace)
        return Response([{"id": str(a.id), "anomaly_type": a.anomaly_type, "severity": a.severity, "summary": a.summary, "evidence": a.evidence, "status": a.status, "detected_at": a.detected_at} for a in workspace.audit_anomalies.all()])

    def patch(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id); require_capability(request.user, workspace, "security.manage")
        row = get_object_or_404(AuditAnomaly, workspace=workspace, id=request.data.get("id"))
        state = request.data.get("status")
        if state not in AuditAnomaly.Status.values: raise ValidationError({"status": "Invalid anomaly status."})
        row.status = state; row.resolved_at = timezone.now() if state == "resolved" else None; row.save(update_fields=["status", "resolved_at"])
        return Response({"id": str(row.id), "status": row.status})


class ComplianceExportListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id); require_capability(request.user, workspace, "compliance.export")
        return Response([{"id": str(e.id), "export_type": e.export_type, "checksum": e.checksum, "created_at": e.created_at} for e in workspace.compliance_exports.all().order_by("-created_at")])

    def post(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id)
        export_type = request.data.get("export_type", "full")
        if export_type not in ComplianceExport.ExportType.values: raise ValidationError({"export_type": "Invalid export type."})
        row = build_compliance_export(workspace, request.user, export_type, parse_datetime(request.data.get("period_start", "")), parse_datetime(request.data.get("period_end", "")))
        return Response({"id": str(row.id), "checksum": row.checksum, "evidence": row.evidence, "created_at": row.created_at}, status=201)


class ExecutionTraceListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        from ai.models import ModelCall

        workspace = get_workspace_for_member(request.user, workspace_id)
        require_capability(request.user, workspace, "audit.read")
        calls = ModelCall.objects.filter(workspace=workspace).select_related("coworker").order_by("-created_at")[:100]
        return Response([{
            "id": str(call.id), "request_id": str(call.request_id),
            "coworker_id": str(call.coworker_id) if call.coworker_id else None,
            "coworker_name": call.coworker.name if call.coworker else None,
            "model_id": call.model_id, "deployment_mode": call.deployment_mode,
            "capability_requested": call.capability_requested,
            "fallback_used": call.fallback_used, "status": call.status,
            "input_tokens": call.input_tokens, "output_tokens": call.output_tokens,
            "latency_ms": call.latency_ms, "created_at": call.created_at,
            "explanation": (
                f"Routed to {call.model_id} via {call.deployment_mode}; "
                f"tool calling was {'requested' if call.capability_requested.get('tool_calling') else 'not requested'}; "
                f"fallback was {'used' if call.fallback_used else 'not needed'}; outcome: {call.status}."
            ),
        } for call in calls])


class CoworkerBundleExportView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, coworker_id):
        coworker = get_coworker_for_member(request.user, coworker_id)
        if evaluate_policy(coworker.workspace, resource_type="coworker", action="export", context={"role": WorkspaceMember.objects.get(workspace=coworker.workspace, user=request.user).role}) == "deny": raise PermissionDenied("Organization policy denied coworker export.")
        artifact = export_coworker_bundle(coworker, request.user)
        return Response({"artifact_id": str(artifact.id), "checksum": artifact.checksum, "bundle": artifact.content}, status=201)


class CoworkerBundleImportView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id)
        require_capability(request.user, workspace, "sdk.manage")
        coworker = import_coworker_bundle(workspace, request.user, request.data.get("bundle", {}))
        return Response({"id": str(coworker.id), "name": coworker.name}, status=201)


class ArtifactListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        workspace = get_workspace_for_member(request.user, request.query_params.get("workspace_id"))
        return Response([{"id": str(a.id), "artifact_type": a.artifact_type, "name": a.name, "content": a.content, "checksum": a.checksum, "created_at": a.created_at} for a in workspace.artifacts.all().order_by("-created_at")])

    def post(self, request):
        workspace = get_workspace_for_member(request.user, request.data.get("workspace_id"))
        artifact_type = request.data.get("artifact_type")
        if artifact_type not in Artifact.ArtifactType.values: raise ValidationError({"artifact_type": "Unsupported artifact type."})
        content = request.data.get("content", {})
        canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
        row = Artifact.objects.create(workspace=workspace, artifact_type=artifact_type, name=request.data.get("name", "Artifact"), content=content, checksum=hashlib.sha256(canonical.encode()).hexdigest(), created_by=request.user, source_coworker_id=request.data.get("coworker_id"))
        return Response({"id": str(row.id), "checksum": row.checksum}, status=201)


class MarketplaceCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, listing_id):
        versions = MarketplaceListingVersion.objects.select_related("listing__publisher_workspace").filter(
            listing_id=listing_id, review_status="approved"
        )
        if request.data.get("version"):
            versions = versions.filter(version_string=request.data["version"])
        version = versions.order_by("-published_at").first()
        if version is None:
            raise ValidationError("No approved listing version is available.")
        workspace = get_workspace_for_member(request.user, request.data.get("workspace_id"))
        amount = version.listing.price_usd or Decimal("0")
        if version.listing.pricing_model == "free": raise ValidationError("Free listings do not require checkout.")
        order = MarketplaceOrder.objects.create(workspace=workspace, listing_version=version, buyer=request.user, amount_usd=amount)
        base = getattr(settings, "PAYMENTS_CHECKOUT_BASE_URL", "")
        checkout_url = f"{base.rstrip('/')}/{order.id}" if base else None
        return Response({"order_id": str(order.id), "amount_usd": str(amount), "checkout_url": checkout_url, "status": order.status}, status=201)


class MarketplacePaymentWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        secret = getattr(settings, "PAYMENTS_WEBHOOK_SECRET", "")
        expected = hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
        if not secret or not hmac.compare_digest(request.headers.get("X-Agentarium-Payment-Signature", ""), expected): return Response({"error": "invalid_signature"}, status=401)
        order = get_object_or_404(MarketplaceOrder, id=request.data.get("order_id"))
        complete_marketplace_order(order, request.data.get("provider_reference", ""))
        install_dependencies(order.listing_version, workspace=order.workspace, user=order.buyer)
        install_listing(order.listing_version, workspace=order.workspace, user=order.buyer)
        return Response({"accepted": True, "order_id": str(order.id)})


class PayoutAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id); require_capability(request.user, workspace, "marketplace.payouts")
        account = PayoutAccount.objects.filter(workspace=workspace).first()
        payouts = MarketplacePayout.objects.filter(publisher_workspace=workspace)
        return Response({"account": {"provider": account.provider, "provider_account_id": account.provider_account_id, "enabled": account.enabled} if account else None, "payouts": [{"id": str(p.id), "listing": p.listing.name, "gross_usd": str(p.gross_usd), "platform_fee_usd": str(p.platform_fee_usd), "net_payout_usd": str(p.net_payout_usd), "status": p.status, "created_at": p.created_at} for p in payouts]})

    def post(self, request, workspace_id):
        workspace = get_workspace_for_member(request.user, workspace_id); require_capability(request.user, workspace, "marketplace.payouts")
        account, _ = PayoutAccount.objects.update_or_create(workspace=workspace, defaults={"provider": request.data.get("provider", "external"), "provider_account_id": request.data.get("provider_account_id", ""), "enabled": True})
        return Response({"id": str(account.id), "enabled": account.enabled}, status=201)
