from types import SimpleNamespace
from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ai.team_designer import TeamDesignError, _extract_json, _sanitize
from core.coworkers import create_coworker
from core.models import Coworker, User
from core.provisioning import DEFAULT_MODEL_BINDING, provision_personal_workspace

VALID_PASSWORD = "correct horse battery staple 42"

TOOLS = {"web_search", "read_file", "write_file", "execute_code"}


class StarterTeamApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="teams@example.com", password=VALID_PASSWORD)
        self.workspace = provision_personal_workspace(self.user)
        self.client.force_authenticate(user=self.user)

    def test_template_catalog_is_empty(self):
        existing = create_coworker(
            workspace=self.workspace,
            owner=self.user,
            owner_type=Coworker.OwnerType.USER,
            name="User-created coworker",
            role_description="A role created by the user.",
            model_binding=DEFAULT_MODEL_BINDING,
            created_by=self.user,
        )
        response = self.client.get(reverse("team-template-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])
        self.assertTrue(Coworker.objects.filter(id=existing.id).exists())

    def test_removed_template_cannot_create_coworkers(self):
        response = self.client.post(
            reverse("provision-team", kwargs={"workspace_id": self.workspace.id}),
            {"template": "software"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Coworker.objects.filter(workspace=self.workspace).exists())

    def test_provision_custom_spec_matches_template_path(self):
        spec = {
            "team_name": "Design pod",
            "collaboration_pattern": "sequential",
            "coworkers": [
                {"name": "Researcher", "team_role": "researcher", "role_description": "You research design trends.", "tools": ["web_search"]},
                {"name": "Designer", "team_role": "custom", "custom_role_label": "Designer", "role_description": "You produce design briefs.", "tools": ["write_file", "not_a_real_tool"]},
            ],
        }
        response = self.client.post(
            reverse("provision-team", kwargs={"workspace_id": self.workspace.id}),
            spec,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIsNotNone(response.data["team_id"])
        designer = Coworker.objects.get(workspace=self.workspace, name="Designer")
        # Unknown tool names are skipped, not fatal.
        self.assertEqual({row.tool.name for row in designer.tool_attachments.all()}, {"write_file"})

    def test_provision_rejects_unknown_template_and_oversized_spec(self):
        url = reverse("provision-team", kwargs={"workspace_id": self.workspace.id})
        self.assertEqual(
            self.client.post(url, {"template": "nope"}, format="json").status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        big = {
            "coworkers": [
                {"name": f"C{i}", "role_description": "You help."} for i in range(7)
            ]
        }
        self.assertEqual(
            self.client.post(url, big, format="json").status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_provision_requires_membership(self):
        outsider = User.objects.create_user(email="outsider@example.com", password=VALID_PASSWORD)
        self.client.force_authenticate(user=outsider)
        response = self.client.post(
            reverse("provision-team", kwargs={"workspace_id": self.workspace.id}),
            {"template": "solo"},
            format="json",
        )
        self.assertIn(
            response.status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
        )

    def test_suggestions_without_provider_key_returns_clear_error(self):
        response = self.client.post(
            reverse("team-suggestions", kwargs={"workspace_id": self.workspace.id}),
            {"description": "A two-person newsletter studio."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "provider_credential_required")

    def test_suggestions_returns_sanitized_spec(self):
        proposal = """```json
        {"team_name": "Newsletter crew", "collaboration_pattern": "manager_delegate",
         "coworkers": [
            {"name": "Editor in chief", "team_role": "editor", "role_description": "You run the newsletter.", "tools": ["web_search", "fake_tool"]},
            {"name": "Writer", "team_role": "writer", "role_description": "You draft issues.", "tools": ["write_file"]}
         ]}
        ```"""
        fake_router = SimpleNamespace(generate=lambda *a, **k: SimpleNamespace(content=proposal))
        with patch("ai.team_designer.build_model_router", return_value=fake_router):
            response = self.client.post(
                reverse("team-suggestions", kwargs={"workspace_id": self.workspace.id}),
                {"description": "A two-person newsletter studio."},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        spec = response.data
        self.assertEqual(spec["team_name"], "Newsletter crew")
        # "editor" isn't a valid enum role → coerced to custom, and the
        # manager_delegate invariant is repaired by promoting the first member.
        self.assertEqual(spec["coworkers"][0]["team_role"], "manager")
        self.assertEqual(spec["coworkers"][0]["tools"], ["web_search"])


class TeamDesignerUnitTests(APITestCase):
    def test_extract_json_handles_fences_and_prose(self):
        self.assertEqual(_extract_json('```json\n{"a": 1}\n```')["a"], 1)
        self.assertEqual(_extract_json('Here you go: {"a": 2} hope it helps')["a"], 2)
        with self.assertRaises(TeamDesignError):
            _extract_json("no json here at all")

    def test_sanitize_clamps_size_and_demotes_extra_managers(self):
        parsed = {
            "team_name": "Big",
            "collaboration_pattern": "manager_delegate",
            "coworkers": [
                {"name": f"M{i}", "team_role": "manager", "role_description": "You manage."}
                for i in range(8)
            ],
        }
        spec = _sanitize(parsed, TOOLS)
        self.assertEqual(len(spec["coworkers"]), 6)
        managers = [m for m in spec["coworkers"] if m["team_role"] == "manager"]
        self.assertEqual(len(managers), 1)

    def test_sanitize_normalizes_aliases_and_defaults_tools(self):
        parsed = {
            "team_name": "Eng",
            "collaboration_pattern": "sequential",
            "coworkers": [
                {"name": "Dev", "team_role": "developer", "role_description": "You build.", "tools": ["python", "search"]},
                {"name": "Helper", "team_role": "researcher", "role_description": "You help.", "tools": ["totally_unknown_tool"]},
            ],
        }
        spec = _sanitize(parsed, TOOLS)
        dev = spec["coworkers"][0]
        # "python" -> execute_code, "search" -> web_search
        self.assertEqual(set(dev["tools"]), {"execute_code", "web_search"})
        helper = spec["coworkers"][1]
        # All tool names unusable -> safe defaults (researcher gets no sandbox).
        self.assertEqual(set(helper["tools"]), {"web_search", "read_file", "write_file"})

    def test_sanitize_rejects_empty_proposals(self):
        with self.assertRaises(TeamDesignError):
            _sanitize({"coworkers": []}, TOOLS)
        with self.assertRaises(TeamDesignError):
            _sanitize({"coworkers": [{"name": "", "role_description": ""}]}, TOOLS)
