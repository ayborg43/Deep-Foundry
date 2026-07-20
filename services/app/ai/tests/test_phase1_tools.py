from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from ai.sandbox import _decode_logs
from ai.web_reader import (
    WebPageError,
    _FetchedPage,
    _ReadableHTMLParser,
    _fetch_url,
    _validated_target,
    fetch_public_resource,
    read_webpage,
)
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


class WebPageReaderTests(SimpleTestCase):
    @override_settings(WEB_READER_MAX_HEADINGS=30, WEB_READER_MAX_LINKS=50)
    def test_extracts_readable_article_and_metadata(self):
        parser = _ReadableHTMLParser("https://example.com/posts/one")
        parser.feed(
            """
            <html lang="en"><head>
              <title>Example report</title>
              <meta name="description" content="A concise report.">
              <link rel="canonical" href="/canonical">
              <script>ignore_secret_script_text()</script>
            </head><body>
              <nav>Navigation noise</nav>
              <main>
                <h1>Key finding</h1>
                <p>The useful evidence is here.</p>
                <a href="/source#section">Primary source</a>
              </main>
            </body></html>
            """
        )
        self.assertEqual(parser.title, "Example report")
        self.assertEqual(parser.description, "A concise report.")
        self.assertEqual(parser.canonical_url, "https://example.com/canonical")
        self.assertEqual(parser.language, "en")
        self.assertIn("The useful evidence is here.", parser.readable_text())
        self.assertNotIn("Navigation noise", parser.readable_text())
        self.assertNotIn("ignore_secret", parser.readable_text())
        self.assertEqual(parser.headings, [{"level": 1, "text": "Key finding"}])
        self.assertEqual(
            parser.links,
            [{"text": "Primary source", "url": "https://example.com/source"}],
        )

    @patch("ai.web_reader.socket.getaddrinfo")
    def test_accepts_only_globally_routable_targets(self, getaddrinfo):
        getaddrinfo.return_value = [
            (2, 1, 6, "", ("93.184.216.34", 443)),
        ]
        parsed, address, port = _validated_target("https://example.com/report")
        self.assertEqual(parsed.hostname, "example.com")
        self.assertEqual(address, "93.184.216.34")
        self.assertEqual(port, 443)

    @patch("ai.web_reader.socket.getaddrinfo")
    def test_blocks_private_or_mixed_dns_answers(self, getaddrinfo):
        getaddrinfo.return_value = [
            (2, 1, 6, "", ("93.184.216.34", 443)),
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ]
        with self.assertRaisesRegex(WebPageError, "private"):
            _validated_target("https://example.com/report")

    def test_blocks_credentials_non_http_schemes_and_custom_ports(self):
        blocked = (
            "file:///etc/passwd",
            "https://user:password@example.com/",
            "http://example.com:8080/",
        )
        for url in blocked:
            with self.subTest(url=url), self.assertRaises(WebPageError):
                _validated_target(url)

    @patch("ai.web_reader._request_once")
    def test_blocks_https_redirect_downgrade(self, request_once):
        request_once.return_value = (
            302,
            {"location": "http://example.com/insecure"},
            b"",
        )
        with self.assertRaisesRegex(WebPageError, "insecure HTTP"):
            _fetch_url("https://example.com/start")

    @patch("ai.web_reader._validated_target")
    @patch("ai.web_reader._request_once")
    def test_workspace_blocklist_is_rechecked_on_redirect(
        self, request_once, validated_target
    ):
        from urllib.parse import urlsplit

        request_once.return_value = (
            302,
            {"location": "https://blocked.example/report"},
            b"",
        )
        validated_target.return_value = (
            urlsplit("https://blocked.example/report"),
            "93.184.216.34",
            443,
        )
        with self.assertRaisesRegex(WebPageError, "research policy"):
            fetch_public_resource(
                "https://allowed.example/start",
                allowed_content_types={"text/html"},
                blocked_domains=["blocked.example"],
            )

    @patch("ai.web_reader._fetch_url")
    @override_settings(WEB_READER_MAX_TEXT_CHARS=30000)
    def test_read_webpage_bounds_model_facing_text(self, fetch_url):
        fetch_url.return_value = _FetchedPage(
            requested_url="https://example.com",
            final_url="https://example.com/final",
            status_code=200,
            content_type="text/html",
            charset="utf-8",
            body=(
                b"<html><head><title>Long page</title></head><body><main><p>"
                + b"x" * 1500
                + b"</p></main></body></html>"
            ),
        )
        page = read_webpage("https://example.com", max_chars=1000)
        self.assertTrue(page["truncated"])
        self.assertEqual(page["title"], "Long page")
        self.assertIn("Content truncated", page["text"])
        self.assertLess(len(page["text"]), 1100)


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
