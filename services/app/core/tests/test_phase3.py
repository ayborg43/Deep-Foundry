import hashlib
import hmac
import json
from unittest.mock import patch

from django.core import signing
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from core.coworkers import create_coworker
from core.encryption import encrypt_to_bytes
from core.models import (
    AuditLog, MarketplaceListing, MarketplaceListingVersion, MarketplaceOrder,
    MarketplacePayout, MarketplaceSecurityReview, OrganizationPolicyRule,
    PermissionProfile, SSOProvider, User, WorkflowRun, Workspace, WorkspaceMember,
)
from core.v2_engine import advance_workflow_run
from core.v2_services import create_workflow, publish_listing_version, start_workflow_run
from core.v3_services import (
    build_compliance_export, detect_audit_anomalies, export_coworker_bundle,
    import_coworker_bundle, require_capability, scan_listing_version,
)


class Phase3Base(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="enterprise-owner@example.com", password="safe-test-password-123")
        self.workspace = Workspace.objects.create(name="Enterprise", type="organization", owner=self.owner, plan_tier="cloud_enterprise")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.owner, role="owner")
        profile = PermissionProfile.objects.create(workspace=self.workspace, name="Default")
        self.coworker = create_coworker(workspace=self.workspace, owner=self.owner, created_by=self.owner, name="Portable Analyst", role_description="Analyze evidence without leaking private memory.", model_binding={"primary": "deepseek-v4-flash"}, permission_profile=profile)
        self.client = APIClient(); self.client.force_authenticate(self.owner)


class EnterpriseIdentityTests(Phase3Base):
    def test_delegated_security_admin_has_security_but_not_billing_capability(self):
        admin = User.objects.create_user(email="security@example.com", password="safe-test-password-123")
        WorkspaceMember.objects.create(workspace=self.workspace, user=admin, role="security_admin")
        self.assertEqual(require_capability(admin, self.workspace, "security.manage").role, "security_admin")
        with self.assertRaises(Exception): require_capability(admin, self.workspace, "billing.manage")

    def test_scim_token_provisions_and_deactivates_user(self):
        created = self.client.post(f"/api/v1/workspaces/{self.workspace.id}/scim-tokens", {"name": "Okta"}, format="json")
        scim = APIClient(); scim.credentials(HTTP_AUTHORIZATION=f"Bearer {created.data['token']}")
        provisioned = scim.post("/api/v1/scim/v2/Users", {"userName": "new.employee@example.com", "displayName": "New Employee", "roles": [{"value": "member"}]}, format="json")
        self.assertEqual(provisioned.status_code, 201)
        disabled = scim.patch(f"/api/v1/scim/v2/Users/{provisioned.data['id']}", {"Operations": [{"op": "replace", "path": "active", "value": False}]}, format="json")
        self.assertEqual(disabled.status_code, 200); self.assertFalse(User.objects.get(id=provisioned.data["id"]).is_active)

    def test_signed_saml_broker_assertion_jit_provisions_member(self):
        provider = SSOProvider.objects.create(workspace=self.workspace, name="SAML", protocol="saml", issuer="https://idp.example", sso_url="https://idp.example/login", entity_id="agentarium-enterprise", encrypted_secret=encrypt_to_bytes("broker-secret"), email_domains=["example.com"])
        state = signing.dumps({"provider_id": str(provider.id), "nonce": "test"}, salt="enterprise-sso")
        assertion = {"issuer": provider.issuer, "audience": provider.entity_id, "email": "sso.user@example.com", "display_name": "SSO User"}
        signature = hmac.new(b"broker-secret", json.dumps(assertion, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
        response = APIClient().post(f"/api/v1/sso/{provider.id}/callback", {"state": state, "assertion": assertion, "signature": signature}, format="json")
        self.assertEqual(response.status_code, 200); self.assertTrue(WorkspaceMember.objects.filter(workspace=self.workspace, user__email="sso.user@example.com").exists())


class GovernanceTests(Phase3Base):
    def test_compliance_export_is_checksum_protected_and_excludes_secrets(self):
        AuditLog.objects.create(workspace=self.workspace, actor_type="user", actor_id=self.owner.id, action="policy.change", resource_type="workspace", resource_id=self.workspace.id)
        export = build_compliance_export(self.workspace, self.owner, "full")
        canonical = json.dumps(export.evidence, sort_keys=True, separators=(",", ":"))
        self.assertEqual(export.checksum, hashlib.sha256(canonical.encode()).hexdigest())
        self.assertNotIn("encrypted_secret", canonical)

    def test_activity_spike_creates_one_deduplicated_anomaly(self):
        AuditLog.objects.bulk_create([AuditLog(workspace=self.workspace, actor_type="user", actor_id=self.owner.id, action="resource.read", resource_type="project") for _ in range(50)])
        self.assertEqual(len(detect_audit_anomalies(self.workspace)), 1)
        self.assertEqual(len(detect_audit_anomalies(self.workspace)), 0)

    @patch("worker.tasks.execute_workflow_run.delay")
    def test_conditional_workflow_skips_to_false_branch_without_eval(self, _delay):
        workflow = create_workflow(workspace=self.workspace, user=self.owner, name="Conditional", definition={"steps": [{"type": "condition", "condition": {"path": "priority", "operator": "equals", "value": "high"}, "if_true": 1, "if_false": 2}, {"type": "coworker_action", "coworker_id": str(self.coworker.id), "instructions": "Handle urgent work."}, {"type": "human_checkpoint", "title": "Review"}]})
        run = start_workflow_run(workflow, triggered_by="user", context={"priority": "low"})
        advance_workflow_run(str(run.id)); run.refresh_from_db()
        self.assertEqual(run.current_step_index, 2); self.assertEqual(run.status, WorkflowRun.Status.NEEDS_APPROVAL)


class PortabilityAndMarketplaceTests(Phase3Base):
    def test_coworker_bundle_excludes_memory_and_credentials_and_imports(self):
        artifact = export_coworker_bundle(self.coworker, self.owner)
        self.assertFalse(artifact.content["privacy"]["memory_included"]); self.assertFalse(artifact.content["privacy"]["credentials_included"])
        imported = import_coworker_bundle(self.workspace, self.owner, artifact.content)
        self.assertEqual(imported.current_version.role_description, self.coworker.current_version.role_description)

    def test_missing_dependency_reduces_security_score(self):
        listing = MarketplaceListing.objects.create(publisher_workspace=self.workspace, listing_type="skill", name="Dependent", summary="Dependency test")
        version = MarketplaceListingVersion.objects.create(listing=listing, version_string="1.0.0", manifest={"dependencies": [{"listing_id": "00000000-0000-0000-0000-000000000000"}]})
        review = scan_listing_version(version)
        self.assertLess(review.score, 80); self.assertEqual(review.status, "needs_review")

    @override_settings(PAYMENTS_WEBHOOK_SECRET="payment-secret")
    def test_paid_order_webhook_creates_creator_payout_and_install(self):
        listing = MarketplaceListing.objects.create(publisher_workspace=self.workspace, listing_type="skill", name="Paid Skill", summary="Paid", pricing_model="paid", price_usd="20.00")
        version = publish_listing_version(listing, version_string="1.0.0", manifest={"declared_tools": []}, changelog="launch", instruction_content="Perform this paid skill carefully, transparently, and within granted permissions.")
        buyer = User.objects.create_user(email="buyer@example.com", password="safe-test-password-123")
        buyer_workspace = Workspace.objects.create(name="Buyer", type="organization", owner=buyer)
        WorkspaceMember.objects.create(workspace=buyer_workspace, user=buyer, role="owner")
        order = MarketplaceOrder.objects.create(workspace=buyer_workspace, listing_version=version, buyer=buyer, amount_usd="20.00")
        body = json.dumps({"order_id": str(order.id), "provider_reference": "pay_123"}).encode()
        signature = hmac.new(b"payment-secret", body, hashlib.sha256).hexdigest()
        response = APIClient().generic("POST", "/api/v1/marketplace/payment-webhook", body, content_type="application/json", HTTP_X_AGENTARIUM_PAYMENT_SIGNATURE=signature)
        self.assertEqual(response.status_code, 200); self.assertTrue(MarketplacePayout.objects.filter(order=order, net_payout_usd="17.00").exists()); self.assertTrue(buyer_workspace.marketplace_installs.filter(listing_version=version).exists())
