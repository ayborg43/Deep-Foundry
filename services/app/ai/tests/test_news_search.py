import json
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from ai.news_search import NewsSearchError, search_news
from ai.web_search import WebSearchError, _merge_results, search_web


TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "news-search-tests",
    }
}


def response_with(body: bytes):
    response = MagicMock()
    response.__enter__.return_value = response
    response.read.side_effect = lambda size: body[:size]
    return response


@override_settings(
    CACHES=TEST_CACHES,
    NEWS_SEARCH_ENDPOINT="https://api.gdeltproject.org/api/v2/doc/doc",
    NEWS_SEARCH_TIMEOUT_SECONDS=2,
    NEWS_SEARCH_MAX_RESULTS=5,
    NEWS_SEARCH_MAX_RESPONSE_BYTES=4096,
    NEWS_SEARCH_TIMESPAN="7d",
    NEWS_SEARCH_MIN_INTERVAL_SECONDS=5,
    NEWS_SEARCH_CACHE_SECONDS=900,
)
class GdeltNewsSearchTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch("ai.news_search.urlopen")
    def test_normalizes_gdelt_articles_and_caches_results(self, urlopen):
        urlopen.return_value = response_with(
            json.dumps(
                {
                    "articles": [
                        {
                            "url": "https://news.example/story",
                            "title": "  A major   story ",
                            "seendate": "20260720T103000Z",
                            "domain": "news.example",
                            "language": "English",
                            "sourcecountry": "Nigeria",
                            "socialimage": "https://news.example/image.jpg",
                        }
                    ]
                }
            ).encode()
        )

        first = search_news("latest technology", max_results=3)
        second = search_news("latest technology", max_results=3)

        self.assertEqual(first, second)
        self.assertEqual(first[0]["provider"], "gdelt")
        self.assertEqual(first[0]["title"], "A major story")
        self.assertEqual(first[0]["published_at"], "2026-07-20T10:30:00Z")
        self.assertEqual(first[0]["language"], "en")
        self.assertEqual(first[0]["country"], "Nigeria")
        self.assertIn("mode=ArtList", urlopen.call_args.args[0].full_url)
        self.assertEqual(urlopen.call_count, 1)

    @patch("ai.news_search.urlopen")
    def test_rejects_non_json_provider_response(self, urlopen):
        urlopen.return_value = response_with(b"rate limited")
        with self.assertRaisesRegex(NewsSearchError, "invalid response"):
            search_news("technology")


class CombinedSearchTests(SimpleTestCase):
    def test_interleaves_and_deduplicates_results(self):
        merged = _merge_results(
            [
                {"url": "https://a.example/", "title": "A"},
                {"url": "https://same.example/story", "title": "Web copy"},
            ],
            [
                {"url": "https://b.example", "title": "B"},
                {"url": "https://same.example/story/", "title": "News copy"},
            ],
            limit=5,
        )
        self.assertEqual([item["title"] for item in merged], ["A", "B", "Web copy"])

    @override_settings(NEWS_SEARCH_ENABLED=True, WEB_SEARCH_MAX_RESULTS=5)
    @patch("ai.web_search.search_news")
    @patch("ai.web_search._search_duckduckgo")
    def test_blends_news_into_normal_web_search(self, duckduckgo, news):
        duckduckgo.return_value = [{"url": "https://web.example", "title": "Web"}]
        news.return_value = [{"url": "https://news.example", "title": "News"}]
        self.assertEqual(
            [item["title"] for item in search_web("world news")],
            ["Web", "News"],
        )

    @override_settings(NEWS_SEARCH_ENABLED=True, WEB_SEARCH_MAX_RESULTS=5)
    @patch("ai.web_search.search_news")
    @patch("ai.web_search._search_duckduckgo")
    def test_uses_news_when_web_provider_fails(self, duckduckgo, news):
        duckduckgo.side_effect = WebSearchError("web unavailable")
        news.return_value = [{"url": "https://news.example", "title": "News"}]
        self.assertEqual(search_web("world news")[0]["title"], "News")
