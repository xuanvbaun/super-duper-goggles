import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import daily_report


class FakeQuery:
    def __init__(self, result=None, error=None):
        self.result = result or []
        self.error = error

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        if self.error:
            raise self.error
        return self.result


class FakeSession:
    def __init__(self, query):
        self._query = query
        self.closed = False

    def query(self, *args, **kwargs):
        return self._query

    def close(self):
        self.closed = True


class DailyReportSecurityTests(unittest.TestCase):
    def test_untrusted_article_fields_are_safely_rendered(self):
        article = SimpleNamespace(
            rule_score=88,
            source_name='<img src=x onerror="alert(1)">',
            ai_category='<svg onload="alert(2)">',
            source_category="备用分类",
            title='<script>alert("title")</script>',
            ai_summary='<script>alert("summary")</script> enough text',
            raw_summary="原始摘要内容足够长，不会触发链接回退。",
            ai_tags='<b onclick="alert(3)">标签</b>,安全',
            url='javascript:alert("link")',
            published_at=None,
            id="article-1",
            corroborating_sources=None,
            verification_status="single_source",
            corroboration_count=1,
        )
        session = FakeSession(FakeQuery([article]))

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "app.database.get_session", return_value=session
        ), patch.object(daily_report, "_CACHE_DIR", Path(temp_dir)):
            rendered = daily_report.generate_yesterday_html()

        self.assertTrue(session.closed)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img src=x", rendered)
        self.assertNotIn("<svg onload", rendered)
        self.assertNotIn("javascript:", rendered)
        self.assertIn("&lt;script&gt;alert", rendered)
        self.assertIn("&lt;img src=x", rendered)
        self.assertIn("&lt;svg onload", rendered)
        self.assertIn("href=\"#\"", rendered)
        self.assertIn('rel="noopener noreferrer"', rendered)

    def test_http_url_is_escaped_for_attribute_context(self):
        safe_url = daily_report._safe_http_url(
            'https://example.com/read?a=1&label="news"'
        )

        self.assertEqual(
            safe_url,
            "https://example.com/read?a=1&amp;label=&quot;news&quot;",
        )

    def test_database_session_closes_when_query_fails(self):
        session = FakeSession(FakeQuery(error=RuntimeError("query failed")))

        with patch("app.database.get_session", return_value=session):
            with self.assertRaisesRegex(RuntimeError, "query failed"):
                daily_report.generate_yesterday_html()

        self.assertTrue(session.closed)


if __name__ == "__main__":
    unittest.main()
