from __future__ import annotations

import io
import json
import zipfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from ai.document_reader import DocumentReadError, read_public_document
from ai.models import Conversation, Message
from ai.structured_extraction import (
    ExtractionError,
    extraction_to_csv,
    validate_field_schema,
)
from ai.web_crawler import CrawlError, crawl_website
from ai.web_reader import PublicResource
from ai.tool_executor import _read_document
from core.models import Notification, User, Workspace, WorkspaceMember
from research.citations import attach_message_citations
from research.models import (
    ResearchRun,
    ResearchDomainPolicy,
    WebsiteMonitor,
    WebsiteMonitorRun,
)
from research.services import execute_monitor_run, execute_research_run


def create_workspace(email: str = "owner@example.com"):
    user = User.objects.create_user(email=email, password="test-password-123")
    workspace = Workspace.objects.create(
        name="Research workspace",
        type=Workspace.WorkspaceType.PERSONAL,
        owner=user,
    )
    WorkspaceMember.objects.create(
        workspace=workspace,
        user=user,
        role=WorkspaceMember.Role.OWNER,
    )
    return user, workspace


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class CrawlerTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("ai.web_crawler.read_webpage")
    @patch("ai.web_crawler.fetch_public_resource")
    def test_robots_404_allows_bounded_crawl(self, fetch, read):
        fetch.return_value = PublicResource(
            requested_url="https://example.com/robots.txt",
            final_url="https://example.com/robots.txt",
            status_code=404,
            content_type="text/plain",
            charset="utf-8",
            body=b"",
            headers={},
        )
        read.return_value = {
            "requested_url": "https://example.com/",
            "url": "https://example.com/",
            "canonical_url": "",
            "status_code": 200,
            "content_type": "text/html",
            "language": "en",
            "title": "Example",
            "description": "",
            "text": "A sufficiently long public example paragraph for crawler evidence.",
            "headings": [],
            "links": [],
            "truncated": False,
        }
        result = crawl_website(
            "https://example.com",
            controls={"max_pages": 1, "max_depth": 0, "rate_limit_seconds": 0},
        )
        self.assertEqual(len(result["pages"]), 1)
        self.assertEqual(result["robots_status"], 404)
        self.assertTrue(result["pages"][0]["robots_allowed"])

    @patch("ai.web_crawler.fetch_public_resource")
    def test_robots_403_fails_closed(self, fetch):
        fetch.return_value = PublicResource(
            requested_url="https://example.com/robots.txt",
            final_url="https://example.com/robots.txt",
            status_code=403,
            content_type="text/plain",
            charset="utf-8",
            body=b"",
            headers={},
        )
        with self.assertRaisesMessage(CrawlError, "robots.txt"):
            crawl_website(
                "https://example.com",
                controls={"max_pages": 1, "rate_limit_seconds": 0},
            )


class DocumentReaderTests(TestCase):
    @patch("ai.document_reader.PdfReader")
    @patch("ai.document_reader.fetch_public_resource")
    def test_pdf_preserves_page_locators(self, fetch, reader):
        fetch.return_value = PublicResource(
            requested_url="https://example.com/report.pdf",
            final_url="https://example.com/report.pdf",
            status_code=200,
            content_type="application/pdf",
            charset="utf-8",
            body=b"%PDF-test",
            headers={},
        )
        reader.return_value.pages = [
            SimpleNamespace(extract_text=lambda: "First page evidence"),
            SimpleNamespace(extract_text=lambda: "Second page evidence"),
        ]
        result = read_public_document("https://example.com/report.pdf")
        self.assertEqual(result["segments"][1]["page_number"], 2)
        self.assertEqual(result["segments"][1]["locator"], "Page 2")

    @patch("ai.document_reader.fetch_public_resource")
    def test_docx_is_read_without_external_relationships(self, fetch):
        body = io.BytesIO()
        with zipfile.ZipFile(body, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "word/document.xml",
                (
                    '<?xml version="1.0"?>'
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/'
                    'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'
                    "Public report text"
                    "</w:t></w:r></w:p></w:body></w:document>"
                ),
            )
        fetch.return_value = PublicResource(
            requested_url="https://example.com/report.docx",
            final_url="https://example.com/report.docx",
            status_code=200,
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            charset="utf-8",
            body=body.getvalue(),
            headers={},
        )
        result = read_public_document("https://example.com/report.docx")
        self.assertIn("Public report text", result["text"])


class StructuredExtractionTests(TestCase):
    def test_schema_rejects_nested_objects(self):
        with self.assertRaises(ExtractionError):
            validate_field_schema({"company": {"name": ""}})

    def test_csv_export_escapes_formulas(self):
        output = extraction_to_csv({"company": "=IMPORTXML(A1)", "features": ["safe"]})
        self.assertIn("'=IMPORTXML", output)


class CitationTests(TestCase):
    def test_tool_evidence_becomes_verified_message_citation(self):
        user, workspace = create_workspace()
        conversation = Conversation.objects.create(
            workspace=workspace,
            created_by=user,
            title="Research",
        )
        user_message = Message.objects.create(
            conversation=conversation,
            sender_type=Message.SenderType.USER,
            sender_id=user.id,
            content="What is the example?",
        )
        tool_parent = Message.objects.create(
            conversation=conversation,
            sender_type=Message.SenderType.COWORKER,
            tool_calls=[{"id": "call-1", "name": "read_webpage", "arguments": {}}],
        )
        passage = "Example evidence is stored exactly and can be verified by the reader."
        Message.objects.create(
            conversation=conversation,
            sender_type=Message.SenderType.SYSTEM,
            content=json.dumps(
                {
                    "url": "https://example.com/",
                    "title": "Example",
                    "text": passage,
                    "content_type": "text/html",
                }
            ),
            tool_call_id="call-1",
            parent_message=tool_parent,
        )
        answer = Message.objects.create(
            conversation=conversation,
            sender_type=Message.SenderType.COWORKER,
            content="The result is supported by the example source [S1].",
        )
        citations = attach_message_citations(answer, query=user_message.content)
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0].evidence.passage, passage)
        self.assertEqual(citations[0].evidence.source.url, "https://example.com/")
        self.assertEqual(
            citations[0].claim,
            "The result is supported by the example source.",
        )

    def test_search_snippet_is_not_promoted_to_verified_evidence(self):
        user, workspace = create_workspace()
        conversation = Conversation.objects.create(
            workspace=workspace,
            created_by=user,
            title="Search only",
        )
        Message.objects.create(
            conversation=conversation,
            sender_type=Message.SenderType.USER,
            sender_id=user.id,
            content="Search for an example",
        )
        Message.objects.create(
            conversation=conversation,
            sender_type=Message.SenderType.SYSTEM,
            tool_call_id="call-search",
            content=json.dumps(
                {
                    "results": [
                        {
                            "url": "https://example.com/",
                            "title": "Example",
                            "snippet": "Unverified provider snippet",
                        }
                    ]
                }
            ),
        )
        answer = Message.objects.create(
            conversation=conversation,
            sender_type=Message.SenderType.COWORKER,
            content="A search snippet says this [S1].",
        )
        self.assertEqual(attach_message_citations(answer, query="example"), [])


class ResearchExecutionTests(TestCase):
    @patch("worker.tasks.dispatch_notification_email.delay")
    @patch("research.services._run_extraction")
    @patch("research.services._write_report", return_value="# Report\nSupported [S1].")
    @patch("research.services._detect_conflicts", return_value=[])
    @patch("research.services.read_public_document")
    @patch("research.services.search_web")
    @patch("research.services._plan_queries", return_value=["example research"])
    def test_deep_research_persists_progress_sources_and_report(
        self,
        plan,
        search,
        read,
        conflicts,
        report,
        extraction,
        dispatch,
    ):
        user, workspace = create_workspace()
        search.return_value = [
            {"url": "https://example.com/report", "title": "Example", "snippet": "Evidence"}
        ]
        read.return_value = {
            "requested_url": "https://example.com/report",
            "url": "https://example.com/report",
            "title": "Example report",
            "publisher": "Example",
            "published_at": "2026-07-01T00:00:00Z",
            "language": "en",
            "content_type": "text/html",
            "text": (
                "This example report contains a sufficiently detailed supporting passage "
                "for the research question and citation."
            ),
            "headings": [],
            "segments": [],
        }
        run = ResearchRun.objects.create(
            workspace=workspace,
            created_by=user,
            query="example research",
            controls={"minimum_sources": 1},
        )
        execute_research_run(str(run.id))
        run.refresh_from_db()
        self.assertEqual(run.status, ResearchRun.Status.COMPLETED)
        self.assertEqual(run.progress, 100)
        self.assertEqual(run.sources.count(), 1)
        self.assertEqual(run.sources.first().evidence.count(), 1)
        self.assertEqual(
            run.sources.first().evidence.first().claim,
            "Supported.",
        )
        self.assertGreaterEqual(run.steps.count(), 5)
        self.assertTrue(
            Notification.objects.filter(
                user=user,
                type=Notification.Type.RESEARCH_COMPLETED,
            ).exists()
        )


class MonitorTests(TestCase):
    @patch("worker.tasks.dispatch_notification_email.delay")
    @patch("research.services.read_public_document")
    def test_monitor_records_baseline_then_notifies_on_change(self, read, dispatch):
        user, workspace = create_workspace()
        monitor = WebsiteMonitor.objects.create(
            workspace=workspace,
            created_by=user,
            name="Example monitor",
            url="https://example.com/",
            next_run_at=timezone.now(),
        )
        read.return_value = {
            "url": "https://example.com/",
            "title": "Example",
            "text": "Original stable content section.",
        }
        first = WebsiteMonitorRun.objects.create(monitor=monitor)
        execute_monitor_run(str(first.id))
        first.refresh_from_db()
        self.assertFalse(first.change_detected)
        self.assertEqual(monitor.snapshots.count(), 1)

        read.return_value = {
            "url": "https://example.com/",
            "title": "Example",
            "text": "Entirely different updated policy, price, and product details.",
        }
        second = WebsiteMonitorRun.objects.create(monitor=monitor)
        execute_monitor_run(str(second.id))
        second.refresh_from_db()
        self.assertTrue(second.change_detected)
        self.assertTrue(
            Notification.objects.filter(
                user=user,
                type=Notification.Type.WEBSITE_CHANGED,
            ).exists()
        )

    @patch("worker.tasks.dispatch_notification_email.delay")
    @patch("research.services.read_public_document")
    def test_transient_monitor_failure_stays_queued_for_celery_retry(
        self, read, dispatch
    ):
        user, workspace = create_workspace()
        monitor = WebsiteMonitor.objects.create(
            workspace=workspace,
            created_by=user,
            name="Retry monitor",
            url="https://example.com/",
            next_run_at=timezone.now(),
        )
        check = WebsiteMonitorRun.objects.create(monitor=monitor)
        read.side_effect = DocumentReadError("temporary timeout")
        with self.assertRaises(DocumentReadError):
            execute_monitor_run(str(check.id), final_attempt=False)
        check.refresh_from_db()
        self.assertEqual(check.status, WebsiteMonitorRun.Status.QUEUED)
        self.assertFalse(
            Notification.objects.filter(
                user=user,
                type=Notification.Type.MONITOR_FAILED,
            ).exists()
        )
        read.side_effect = None
        read.return_value = {
            "url": "https://example.com/",
            "title": "Recovered",
            "text": "The retry successfully captured public content.",
        }
        execute_monitor_run(str(check.id))
        check.refresh_from_db()
        self.assertEqual(check.status, WebsiteMonitorRun.Status.COMPLETED)
        self.assertEqual(check.error_message, "")


class WorkspaceResearchPolicyTests(TestCase):
    @patch("ai.tool_executor.read_public_document")
    def test_direct_document_tool_enforces_workspace_blocklist(self, read):
        _, workspace = create_workspace()
        ResearchDomainPolicy.objects.create(
            workspace=workspace,
            blocked_domains=["example.com"],
        )
        result = _read_document(
            {"url": "https://example.com/report.pdf"},
            workspace_id=workspace.id,
        )
        self.assertIn("workspace research policy", result.error)
        read.assert_not_called()


class ResearchAPITests(TestCase):
    def setUp(self):
        self.user, self.workspace = create_workspace()
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch("worker.tasks.execute_research_run.delay")
    def test_create_and_read_research_run(self, delay):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                "/api/v1/research-runs",
                {
                    "workspace_id": str(self.workspace.id),
                    "query": "Current public evidence about example domains",
                    "controls": {
                        "minimum_sources": 2,
                        "blocked_domains": ["internal.example"],
                    },
                },
                format="json",
            )
        self.assertEqual(response.status_code, 202)
        run_id = response.data["id"]
        detail = self.client.get(f"/api/v1/research-runs/{run_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["controls"]["minimum_sources"], 2)
        delay.assert_called_once_with(run_id)

    def test_other_workspace_run_is_hidden(self):
        other_user, other_workspace = create_workspace("other@example.com")
        run = ResearchRun.objects.create(
            workspace=other_workspace,
            created_by=other_user,
            query="private workspace research",
        )
        response = self.client.get(f"/api/v1/research-runs/{run.id}")
        self.assertEqual(response.status_code, 403)

    def test_workspace_policy_write_requires_admin(self):
        member = User.objects.create_user(
            email="member@example.com", password="test-password-123"
        )
        WorkspaceMember.objects.create(
            workspace=self.workspace,
            user=member,
            role=WorkspaceMember.Role.MEMBER,
        )
        self.client.force_authenticate(member)
        response = self.client.put(
            f"/api/v1/workspaces/{self.workspace.id}/research-policy",
            {
                "trusted_domains": [],
                "blocked_domains": ["example.com"],
                "default_controls": {},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
