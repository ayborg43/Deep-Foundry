from django.test import SimpleTestCase, override_settings

from ai.sandbox import _decode_logs
from ai.web_search import _ResultsParser


class WebSearchParserTests(SimpleTestCase):
    def test_extracts_results_and_unwraps_redirects(self):
        parser = _ResultsParser()
        parser.feed(
            '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com">'
            "Example result</a>"
            '<a class="result__snippet">A useful <b>snippet</b>.</a>'
        )
        self.assertEqual(parser.results[0]["title"], "Example result")
        self.assertEqual(parser.results[0]["url"], "https://example.com")
        self.assertEqual(parser.results[0]["snippet"], "A useful snippet.")


class SandboxLogTests(SimpleTestCase):
    @staticmethod
    def _frame(stream: int, content: bytes) -> bytes:
        return bytes([stream, 0, 0, 0]) + len(content).to_bytes(4, "big") + content

    @override_settings(SANDBOX_MAX_OUTPUT_BYTES=1024)
    def test_separates_docker_stdout_and_stderr_frames(self):
        raw = self._frame(1, b"out\n") + self._frame(2, b"err\n")
        stdout, stderr, truncated = _decode_logs(raw)
        self.assertEqual(stdout, "out\n")
        self.assertEqual(stderr, "err\n")
        self.assertFalse(truncated)
