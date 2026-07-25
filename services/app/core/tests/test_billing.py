from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.billing import PlanLimitExceeded, enforce_coworker_limit, get_active_plan, get_usage
from core.coworkers import create_coworker
from core.models import AgentTeam, AgentTeamMember, Subscription, SubscriptionPlan, User, Workspace
from core.provisioning import DEFAULT_MODEL_BINDING, provision_personal_workspace
from core.v2_services import create_agent_team

VALID_PASSWORD = "correct horse battery staple 42"


def _make_plan(**overrides):
    defaults = {
        "key": "test-plan", "name": "Test Plan", "price_usd": "0",
        "max_coworkers": 1, "max_agent_teams": 1, "max_tasks_per_month": 5, "max_seats": 2,
        "active": True,
    }
    defaults.update(overrides)
    return SubscriptionPlan.objects.create(**defaults)


class BillingTestBase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="billing-owner@example.com", password=VALID_PASSWORD)
        self.workspace = provision_personal_workspace(self.owner)
        self._auth_as(self.owner)

    def _auth_as(self, user, password=VALID_PASSWORD):
        login = self.client.post(reverse("auth-login"), {"email": user.email, "password": password})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['tokens']['access']}")

    def _make_coworker(self, name="Coworker"):
        return create_coworker(
            workspace=self.workspace, owner=self.owner, name=name,
            role_description="Helps.", model_binding=dict(DEFAULT_MODEL_BINDING),
            created_by=self.owner,
        )


class GetActivePlanTests(BillingTestBase):
    def test_new_workspace_lands_on_the_default_plan(self):
        plan = get_active_plan(self.workspace)
        self.assertIsNotNone(plan)
        self.assertTrue(plan.is_default)
        self.assertEqual(self.workspace.subscription.plan_id, plan.id)

    def test_workspace_with_no_subscription_self_heals_onto_default(self):
        bare = Workspace.objects.create(name="Bare", type=Workspace.WorkspaceType.PERSONAL, owner=self.owner)
        self.assertFalse(Subscription.objects.filter(workspace=bare).exists())
        plan = get_active_plan(bare)
        self.assertTrue(plan.is_default)
        self.assertTrue(Subscription.objects.filter(workspace=bare, plan=plan).exists())


class CoworkerLimitTests(BillingTestBase):
    def setUp(self):
        super().setUp()
        plan = _make_plan(key="cw-limit", max_coworkers=1)
        Subscription.objects.filter(workspace=self.workspace).update(plan=plan)

    def test_allows_up_to_the_limit(self):
        self._make_coworker("First")  # should not raise

    def test_blocks_past_the_limit(self):
        self._make_coworker("First")
        with self.assertRaises(PlanLimitExceeded) as ctx:
            self._make_coworker("Second")
        self.assertEqual(ctx.exception.kind, "coworkers")

    def test_api_returns_402_with_upgrade_message(self):
        self._make_coworker("First")
        response = self.client.post(
            reverse("coworker-list-create", kwargs={"workspace_id": self.workspace.id}),
            {
                "name": "Second", "role_description": "Also helps.",
                "model_binding": {"primary": "deepseek-v4-flash"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 402)
        self.assertEqual(response.data["error"]["code"], "plan_limit_reached")


class AgentTeamLimitTests(BillingTestBase):
    def setUp(self):
        super().setUp()
        plan = _make_plan(key="team-limit", max_coworkers=10, max_agent_teams=1)
        Subscription.objects.filter(workspace=self.workspace).update(plan=plan)
        self.manager = self._make_coworker("Manager")
        self.dev = self._make_coworker("Dev")

    def _team_payload(self):
        return {
            "name": "Team", "collaboration_pattern": "manager_delegate",
            "members": [
                {"coworker_id": str(self.manager.id), "role": "manager"},
                {"coworker_id": str(self.dev.id), "role": "developer"},
            ],
        }

    def test_second_team_is_blocked(self):
        create_agent_team(workspace=self.workspace, user=self.owner, payload=self._team_payload())
        with self.assertRaises(PlanLimitExceeded) as ctx:
            create_agent_team(workspace=self.workspace, user=self.owner, payload=self._team_payload())
        self.assertEqual(ctx.exception.kind, "agent_teams")

    def test_api_returns_402(self):
        create_agent_team(workspace=self.workspace, user=self.owner, payload=self._team_payload())
        response = self.client.post(
            reverse("agent-team-list-create"),
            {**self._team_payload(), "workspace_id": str(self.workspace.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 402)


class SeatLimitTests(BillingTestBase):
    def setUp(self):
        super().setUp()
        plan = _make_plan(key="seat-limit", max_seats=1)  # owner already fills it
        Subscription.objects.filter(workspace=self.workspace).update(plan=plan)

    def test_new_invite_is_blocked_when_full(self):
        response = self.client.post(
            reverse("workspace-member-list-create", kwargs={"workspace_id": self.workspace.id}),
            {"email": "new-member@example.com", "role": "member"},
            format="json",
        )
        self.assertEqual(response.status_code, 402)

    def test_reinviting_an_existing_member_is_not_blocked(self):
        # Role change on the owner themself: same membership row, no new seat.
        response = self.client.post(
            reverse("workspace-member-list-create", kwargs={"workspace_id": self.workspace.id}),
            {"email": self.owner.email, "role": "admin"},
            format="json",
        )
        self.assertNotEqual(response.status_code, 402)


class UsageTests(BillingTestBase):
    def test_usage_counts_reflect_workspace_state(self):
        self._make_coworker("A")
        self._make_coworker("B")
        usage = get_usage(self.workspace)
        self.assertEqual(usage["coworkers"], 2)
        self.assertEqual(usage["seats"], 1)


class SubscriptionEndpointTests(BillingTestBase):
    def setUp(self):
        super().setUp()
        self.other_plan = SubscriptionPlan.objects.create(
            key="upgrade-target", name="Upgrade Target", price_usd="9.00", active=True,
        )

    def test_get_reports_plan_and_usage(self):
        response = self.client.get(reverse("subscription-detail", kwargs={"workspace_id": self.workspace.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIsNotNone(response.data["plan"])
        self.assertIn("coworkers", response.data["usage"])

    def test_patch_switches_to_an_active_plan(self):
        response = self.client.patch(
            reverse("subscription-detail", kwargs={"workspace_id": self.workspace.id}),
            {"plan_key": "upgrade-target"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["plan"]["key"], "upgrade-target")

    def test_patch_rejects_unknown_plan(self):
        response = self.client.patch(
            reverse("subscription-detail", kwargs={"workspace_id": self.workspace.id}),
            {"plan_key": "does-not-exist"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_rejects_inactive_plan(self):
        SubscriptionPlan.objects.filter(key="upgrade-target").update(active=False)
        response = self.client.patch(
            reverse("subscription-detail", kwargs={"workspace_id": self.workspace.id}),
            {"plan_key": "upgrade-target"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PlanAdminApiTests(BillingTestBase):
    def test_non_staff_is_forbidden(self):
        response = self.client.get(reverse("plan-admin-list-create"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_create_edit_and_delete_a_plan(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])

        create = self.client.post(
            reverse("plan-admin-list-create"),
            {
                "key": "staff-created", "name": "Staff Created", "price_usd": "5.00",
                "max_coworkers": 3, "max_agent_teams": None, "max_tasks_per_month": None,
                "max_seats": 3,
            },
            format="json",
        )
        self.assertEqual(create.status_code, status.HTTP_201_CREATED, create.data)
        plan_id = create.data["id"]

        edit = self.client.patch(
            reverse("plan-admin-detail", kwargs={"plan_id": plan_id}),
            {"max_coworkers": 7},
            format="json",
        )
        self.assertEqual(edit.status_code, status.HTTP_200_OK, edit.data)
        self.assertEqual(edit.data["max_coworkers"], 7)

        delete = self.client.delete(reverse("plan-admin-detail", kwargs={"plan_id": plan_id}))
        self.assertEqual(delete.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(SubscriptionPlan.objects.filter(id=plan_id).exists())

    def test_deleting_a_plan_with_subscriptions_is_rejected(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        plan = self.workspace.subscription.plan

        response = self.client.delete(reverse("plan-admin-detail", kwargs={"plan_id": plan.id}))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(SubscriptionPlan.objects.filter(id=plan.id).exists())

    def test_setting_is_default_unsets_the_previous_default(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        previous_default = SubscriptionPlan.objects.get(is_default=True)
        challenger = _make_plan(key="new-default", is_default=False)

        response = self.client.patch(
            reverse("plan-admin-detail", kwargs={"plan_id": challenger.id}),
            {"is_default": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        previous_default.refresh_from_db()
        self.assertFalse(previous_default.is_default)


class PlanCatalogViewTests(BillingTestBase):
    def test_lists_only_active_plans(self):
        _make_plan(key="hidden", active=False)
        response = self.client.get(reverse("plan-catalog"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        keys = {row["key"] for row in response.data}
        self.assertNotIn("hidden", keys)
        self.assertIn("free", keys)
