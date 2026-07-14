from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.models import (
    Coworker,
    CoworkerToolAttachment,
    CoworkerVersion,
    Tool,
    User,
    Workspace,
    WorkspaceMember,
)

VALID_PASSWORD = "correct horse battery staple 42"


class CoworkerTestBase(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="cwowner@example.com", password=VALID_PASSWORD)
        self.stranger = User.objects.create_user(
            email="cwstranger@example.com", password=VALID_PASSWORD
        )
        self.workspace = Workspace.objects.create(
            name="CW Workspace", type=Workspace.WorkspaceType.PERSONAL, owner=self.owner
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace, user=self.owner, role=WorkspaceMember.Role.OWNER
        )
        self._auth_as(self.owner)

    def _auth_as(self, user, password=VALID_PASSWORD):
        login = self.client.post(
            reverse("auth-login"), {"email": user.email, "password": password}
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['tokens']['access']}")

    def _list_create_url(self):
        return reverse("coworker-list-create", kwargs={"workspace_id": self.workspace.id})

    def _detail_url(self, coworker_id):
        return reverse("coworker-detail", kwargs={"coworker_id": coworker_id})

    def _create_coworker(self, **overrides):
        body = {
            "name": "Aria",
            "role_description": "Handles customer support triage.",
            "model_binding": {"primary": "deepseek-chat", "fallback": ["deepseek-reasoner"]},
        }
        body.update(overrides)
        response = self.client.post(self._list_create_url(), body, format="json")
        assert response.status_code == status.HTTP_201_CREATED, response.data
        return response.data


class ToolCatalogTests(CoworkerTestBase):
    def test_lists_seeded_builtin_tools(self):
        response = self.client.get(reverse("tool-catalog-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {t["name"] for t in response.data}
        self.assertEqual(
            names,
            {
                "web_search", "read_file", "write_file", "execute_code",
                "send_email", "create_calendar_event", "send_slack_message",
                "send_discord_message", "create_github_issue", "send_webhook",
                "create_presentation", "create_diagram", "record_video_analysis",
            },
        )

    def test_requires_authentication(self):
        self.client.credentials()
        response = self.client.get(reverse("tool-catalog-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class CoworkerCreateTests(CoworkerTestBase):
    def test_create_returns_flattened_coworker_with_version_1(self):
        data = self._create_coworker()
        self.assertEqual(data["name"], "Aria")
        self.assertEqual(data["role_description"], "Handles customer support triage.")
        self.assertEqual(data["model_binding"]["primary"], "deepseek-chat")
        self.assertEqual(data["current_version"], 1)
        self.assertEqual(data["status"], "active")
        self.assertEqual(data["attached_tools"], [])
        # dangerous can never default to auto — SOUL.md §15.2
        self.assertEqual(data["permission_profile"]["dangerous"], "approval")

    def test_create_persists_coworker_and_version_rows(self):
        data = self._create_coworker()
        coworker = Coworker.objects.get(id=data["id"])
        self.assertEqual(coworker.workspace, self.workspace)
        self.assertEqual(coworker.owner_id, self.owner.id)
        self.assertEqual(CoworkerVersion.objects.filter(coworker=coworker).count(), 1)

    def test_create_rejects_unknown_model(self):
        response = self.client.post(
            self._list_create_url(),
            {
                "name": "Bad",
                "role_description": "x",
                "model_binding": {"primary": "gpt-4"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_rejects_unknown_fallback_model(self):
        response = self.client.post(
            self._list_create_url(),
            {
                "name": "Bad",
                "role_description": "x",
                "model_binding": {"primary": "deepseek-chat", "fallback": ["claude"]},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_member_cannot_create(self):
        self._auth_as(self.stranger)
        response = self.client.post(
            self._list_create_url(),
            {"name": "x", "role_description": "x", "model_binding": {"primary": "deepseek-chat"}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CoworkerListTests(CoworkerTestBase):
    def test_list_shows_active_coworkers(self):
        self._create_coworker(name="One")
        self._create_coworker(name="Two")
        response = self.client.get(self._list_create_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({c["name"] for c in response.data}, {"One", "Two"})

    def test_list_excludes_archived(self):
        created = self._create_coworker(name="ToArchive")
        self.client.delete(reverse("coworker-detail", kwargs={"coworker_id": created["id"]}))
        response = self.client.get(self._list_create_url())
        self.assertEqual(response.data, [])

    def test_list_forbidden_for_non_member(self):
        self._auth_as(self.stranger)
        response = self.client.get(self._list_create_url())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CoworkerDetailTests(CoworkerTestBase):
    def test_get_returns_coworker(self):
        created = self._create_coworker()
        response = self.client.get(self._detail_url(created["id"]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], created["id"])

    def test_non_member_forbidden(self):
        created = self._create_coworker()
        self._auth_as(self.stranger)
        response = self.client.get(self._detail_url(created["id"]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_name_only_does_not_create_new_version(self):
        created = self._create_coworker()
        response = self.client.patch(
            reverse("coworker-detail", kwargs={"coworker_id": created["id"]}),
            {"name": "Renamed"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Renamed")
        self.assertEqual(response.data["current_version"], 1)

    def test_patch_role_description_creates_new_version(self):
        created = self._create_coworker()
        response = self.client.patch(
            reverse("coworker-detail", kwargs={"coworker_id": created["id"]}),
            {"role_description": "New role", "changelog": "Tightened scope"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role_description"], "New role")
        self.assertEqual(response.data["current_version"], 2)

        coworker = Coworker.objects.get(id=created["id"])
        self.assertEqual(coworker.versions.count(), 2)
        v1 = coworker.versions.get(version_number=1)
        self.assertEqual(v1.role_description, "Handles customer support triage.")

    def test_patch_model_binding_creates_new_version(self):
        created = self._create_coworker()
        response = self.client.patch(
            reverse("coworker-detail", kwargs={"coworker_id": created["id"]}),
            {"model_binding": {"primary": "deepseek-reasoner"}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["model_binding"]["primary"], "deepseek-reasoner")
        self.assertEqual(response.data["current_version"], 2)

    def test_patch_empty_body_rejected(self):
        created = self._create_coworker()
        response = self.client.patch(
            reverse("coworker-detail", kwargs={"coworker_id": created["id"]}), {}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_stranger_cannot_patch(self):
        created = self._create_coworker()
        self._auth_as(self.stranger)
        response = self.client.patch(
            reverse("coworker-detail", kwargs={"coworker_id": created["id"]}),
            {"name": "Hijacked"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_archives_not_hard_deletes(self):
        created = self._create_coworker()
        response = self.client.delete(
            reverse("coworker-detail", kwargs={"coworker_id": created["id"]})
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        coworker = Coworker.objects.get(id=created["id"])
        self.assertEqual(coworker.status, Coworker.Status.ARCHIVED)


class CoworkerVersionAndRollbackTests(CoworkerTestBase):
    def test_versions_list_ordered_newest_first(self):
        created = self._create_coworker()
        coworker_id = created["id"]
        self.client.patch(
            reverse("coworker-detail", kwargs={"coworker_id": coworker_id}),
            {"role_description": "v2 role"},
            format="json",
        )
        self.client.patch(
            reverse("coworker-detail", kwargs={"coworker_id": coworker_id}),
            {"role_description": "v3 role"},
            format="json",
        )
        versions_url = reverse("coworker-versions", kwargs={"coworker_id": coworker_id})
        response = self.client.get(versions_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        numbers = [v["version_number"] for v in response.data]
        self.assertEqual(numbers, [3, 2, 1])

    def test_rollback_creates_new_version_copying_old_content(self):
        created = self._create_coworker()
        coworker_id = created["id"]
        self.client.patch(
            reverse("coworker-detail", kwargs={"coworker_id": coworker_id}),
            {"role_description": "changed role"},
            format="json",
        )
        response = self.client.post(
            reverse(
                "coworker-version-rollback",
                kwargs={"coworker_id": coworker_id, "version_number": 1},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role_description"], "Handles customer support triage.")
        self.assertEqual(response.data["current_version"], 3)  # new version, not a pointer move

        coworker = Coworker.objects.get(id=coworker_id)
        self.assertEqual(coworker.versions.count(), 3)
        v3 = coworker.versions.get(version_number=3)
        self.assertIn("Rolled back to v1", v3.changelog)

    def test_rollback_to_nonexistent_version_404s(self):
        created = self._create_coworker()
        response = self.client.post(
            reverse(
                "coworker-version-rollback",
                kwargs={"coworker_id": created["id"], "version_number": 99},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_stranger_cannot_rollback(self):
        created = self._create_coworker()
        self._auth_as(self.stranger)
        response = self.client.post(
            reverse(
                "coworker-version-rollback",
                kwargs={"coworker_id": created["id"], "version_number": 1},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CoworkerToolAttachmentTests(CoworkerTestBase):
    def setUp(self):
        super().setUp()
        self.web_search = Tool.objects.get(name="web_search")
        self.execute_code = Tool.objects.get(name="execute_code")

    def test_attach_tool(self):
        created = self._create_coworker()
        response = self.client.post(
            reverse("coworker-tool-attach", kwargs={"coworker_id": created["id"]}),
            {"tool_id": str(self.web_search.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["tool"]["name"], "web_search")
        self.assertTrue(response.data["enabled"])

        detail = self.client.get(reverse("coworker-detail", kwargs={"coworker_id": created["id"]}))
        self.assertEqual(len(detail.data["attached_tools"]), 1)
        self.assertEqual(detail.data["attached_tools"][0]["name"], "web_search")

    def test_attach_is_idempotent_and_updates_config(self):
        created = self._create_coworker()
        url = reverse("coworker-tool-attach", kwargs={"coworker_id": created["id"]})
        first = self.client.post(url, {"tool_id": str(self.web_search.id)}, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post(
            url,
            {"tool_id": str(self.web_search.id), "enabled": False},
            format="json",
        )
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertFalse(second.data["enabled"])
        self.assertEqual(
            CoworkerToolAttachment.objects.filter(coworker_id=created["id"]).count(), 1
        )

    def test_detach_tool(self):
        created = self._create_coworker()
        self.client.post(
            reverse("coworker-tool-attach", kwargs={"coworker_id": created["id"]}),
            {"tool_id": str(self.execute_code.id)},
            format="json",
        )
        response = self.client.delete(
            reverse(
                "coworker-tool-detach",
                kwargs={"coworker_id": created["id"], "tool_id": self.execute_code.id},
            )
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            CoworkerToolAttachment.objects.filter(
                coworker_id=created["id"], tool=self.execute_code
            ).exists()
        )

    def test_stranger_cannot_attach(self):
        created = self._create_coworker()
        self._auth_as(self.stranger)
        response = self.client.post(
            reverse("coworker-tool-attach", kwargs={"coworker_id": created["id"]}),
            {"tool_id": str(self.web_search.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
