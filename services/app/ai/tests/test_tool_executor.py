import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from ai.tool_executor import ToolExecutionError, execute_tool
from ai.sandbox import SandboxResult


class ToolExecutorTests(SimpleTestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self._settings_override = override_settings(WORKSPACE_FILES_ROOT=self._tmpdir.name)
        self._settings_override.enable()
        self.addCleanup(self._settings_override.disable)
        self.workspace_id = uuid.uuid4()

    @patch("ai.tool_executor.search_web")
    def test_web_search_returns_provider_results(self, search_web):
        search_web.return_value = [
            {"title": "Agentarium", "url": "https://example.com", "snippet": "AI coworkers"}
        ]
        result = execute_tool("web_search", {"query": "agentarium"}, workspace_id=self.workspace_id)
        self.assertEqual(result.output["results"][0]["title"], "Agentarium")
        self.assertIsNone(result.error)
        search_web.assert_called_once_with("agentarium", max_results=None)

    def test_write_then_read_file_round_trips(self):
        write_result = execute_tool(
            "write_file",
            {"path": "notes/todo.txt", "content": "hello world"},
            workspace_id=self.workspace_id,
        )
        self.assertEqual(write_result.output["bytes_written"], len("hello world"))

        read_result = execute_tool(
            "read_file", {"path": "notes/todo.txt"}, workspace_id=self.workspace_id
        )
        self.assertEqual(read_result.output["content"], "hello world")

    def test_read_file_missing_raises(self):
        with self.assertRaises(ToolExecutionError):
            execute_tool("read_file", {"path": "nope.txt"}, workspace_id=self.workspace_id)

    def test_read_file_requires_path(self):
        with self.assertRaises(ToolExecutionError):
            execute_tool("read_file", {}, workspace_id=self.workspace_id)

    def test_write_file_path_traversal_is_blocked(self):
        with self.assertRaises(ToolExecutionError):
            execute_tool(
                "write_file",
                {"path": "../../etc/passwd", "content": "pwned"},
                workspace_id=self.workspace_id,
            )

    def test_read_file_path_traversal_is_blocked(self):
        # Prove nothing escaped by planting a real file just outside the
        # per-workspace root and confirming it can't be read back through it.
        root = Path(self._tmpdir.name)
        outside = root / "secret.txt"
        outside.write_text("top secret")
        with self.assertRaises(ToolExecutionError):
            execute_tool(
                "read_file",
                {"path": "../secret.txt"},
                workspace_id=self.workspace_id,
            )

    def test_two_workspaces_are_isolated(self):
        other_workspace_id = uuid.uuid4()
        execute_tool(
            "write_file",
            {"path": "a.txt", "content": "workspace one"},
            workspace_id=self.workspace_id,
        )
        with self.assertRaises(ToolExecutionError):
            execute_tool("read_file", {"path": "a.txt"}, workspace_id=other_workspace_id)

    @patch("ai.tool_executor.run_python")
    def test_execute_code_returns_sandbox_result(self, run_python):
        run_python.return_value = SandboxResult("hello\n", "", 0)
        result = execute_tool(
            "execute_code",
            {"language": "python", "code": "print('hello')"},
            workspace_id=self.workspace_id,
        )
        self.assertIsNone(result.error)
        self.assertEqual(result.output["stdout"], "hello\n")
        self.assertEqual(result.output["exit_code"], 0)

    def test_execute_code_rejects_unsupported_language(self):
        result = execute_tool(
            "execute_code",
            {"language": "javascript", "code": "console.log('no')"},
            workspace_id=self.workspace_id,
        )
        self.assertIn("Unsupported", result.error)

    def test_unknown_tool_raises(self):
        with self.assertRaises(ToolExecutionError):
            execute_tool("delete_universe", {}, workspace_id=self.workspace_id)
