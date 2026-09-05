import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import NewsArticle
from app.rule_engine import calculate_credibility_score


class CredibilityScoreTests(unittest.TestCase):
    def test_sqlite_naive_timestamp_can_be_scored(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            article = NewsArticle(
                title="测试新闻",
                url="https://example.com/article",
                source_name="测试源",
                source_credibility=4,
                raw_summary="摘要",
                published_at=datetime.now(timezone.utc) - timedelta(hours=48),
                ai_processed=False,
            )
            session.add(article)
            session.commit()
            session.refresh(article)
            self.assertIsNone(article.published_at.tzinfo)

            config = SimpleNamespace(
                rule_engine=SimpleNamespace(
                    source_weight=0.35,
                    corroboration_weight=0.30,
                    freshness_weight=0.15,
                    completeness_weight=0.2,
                    official_bonus=8.0,
                )
            )
            with patch("app.rule_engine.get_config", return_value=config):
                score = calculate_credibility_score(article)

        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)


if __name__ == "__main__":
    unittest.main()
