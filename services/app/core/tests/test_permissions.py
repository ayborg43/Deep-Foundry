from django.test import SimpleTestCase
from itertools import product

from core.models import Tool
from core.permissions import resolve_tool_permission


class ResolveToolPermissionTests(SimpleTestCase):
    """SECURITY.md §4 / SOUL.md §15.2: `dangerous` tools can never auto-execute.
    This is the single evaluation point everything else (chat orchestration,
    tool executor, worker tasks) is expected to call — these tests exist so a
    future change to this function can't silently reopen the bypass."""

    def test_safe_tool_honors_stored_policy(self):
        self.assertEqual(
            resolve_tool_permission(Tool.RiskClassification.SAFE, {"safe": "auto"}), "auto"
        )

    def test_sensitive_tool_honors_stored_policy(self):
        self.assertEqual(
            resolve_tool_permission(
                Tool.RiskClassification.SENSITIVE, {"sensitive": "approval"}
            ),
            "approval",
        )

    def test_dangerous_tool_always_requires_approval(self):
        self.assertEqual(
            resolve_tool_permission(
                Tool.RiskClassification.DANGEROUS, {"dangerous": "approval"}
            ),
            "approval",
        )

    def test_dangerous_tool_ignores_a_corrupted_auto_policy(self):
        """A stored policy of {"dangerous": "auto"} should be unreachable in
        practice (PermissionProfile.save() rejects it), but this function must
        not trust that — it's the backstop if that write-path check is ever
        bypassed (direct DB write, a future code path that skips .save())."""
        self.assertEqual(
            resolve_tool_permission(Tool.RiskClassification.DANGEROUS, {"dangerous": "auto"}),
            "approval",
        )

    def test_unknown_risk_classification_fails_closed(self):
        self.assertEqual(resolve_tool_permission("unknown", {}), "approval")

    def test_missing_policy_key_fails_closed(self):
        self.assertEqual(resolve_tool_permission(Tool.RiskClassification.SENSITIVE, {}), "approval")

    def test_dangerous_is_blocked_under_every_coworker_and_org_policy_combination(self):
        policies = (
            {},
            {"dangerous": "approval"},
            {"dangerous": "auto"},
            {"dangerous": "allow"},
            {"safe": "auto", "sensitive": "auto", "dangerous": "auto"},
        )
        for coworker_policy, org_policy in product(policies, repeat=2):
            with self.subTest(coworker=coworker_policy, org=org_policy):
                self.assertEqual(
                    resolve_tool_permission(
                        Tool.RiskClassification.DANGEROUS,
                        coworker_policy,
                        org_policy,
                    ),
                    "approval",
                )

    def test_org_floor_can_raise_but_never_lower_approval_strictness(self):
        self.assertEqual(
            resolve_tool_permission("safe", {"safe": "auto"}, {"safe": "approval"}),
            "approval",
        )
        self.assertEqual(
            resolve_tool_permission("safe", {"safe": "approval"}, {"safe": "auto"}),
            "approval",
        )
