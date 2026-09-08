from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app import crud
from app.database import Base
from app.models import NewsArticle


@pytest.fixture
def stats_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with patch.object(crud, "get_session", sessions), patch.object(
        crud, "app_timezone", return_value=ZoneInfo("Asia/Shanghai")
    ), patch("app.time_utils.app_timezone", return_value=ZoneInfo("Asia/Shanghai")), patch.object(
        crud, "datetime"
    ) as clock:
        clock.now.return_value = datetime(2026, 9, 8, 12, tzinfo=ZoneInfo("Asia/Shanghai"))
        yield engine, sessions
    engine.dispose()


def add_articles(sessions, rows):
    with sessions.begin() as session:
        for i, row in enumerate(rows):
            session.add(NewsArticle(
                title=f"Article {i}", url=f"https://example.com/{i}",
                **{"source_name": "Source A", **row},
            ))


def test_empty_stats(stats_db):
    assert crud.get_stats() == {
        "total_articles": 0, "ai_processed_count": 0, "categories": {},
        "sources_count": 0, "latest_fetch": None, "today": None,
        "yesterday": None, "daily": [], "multi_source_articles": 0,
        "official_confirmed_articles": 0,
    }


def test_stats_counts_categories_and_local_day_boundaries(stats_db):
    _, sessions = stats_db
    start = datetime(2026, 9, 7, 16)  # September 8 midnight in Shanghai.
    add_articles(sessions, [
        dict(fetched_at=start, ai_category="科技", source_category="综合",
             ai_processed=True, corroboration_count=2, official_confirmed=True),
        dict(fetched_at=start + timedelta(days=1, microseconds=-1),
             ai_category="", source_category="科技"),
        dict(fetched_at=start - timedelta(microseconds=1), source_category=""),
        dict(fetched_at=start - timedelta(days=6), source_category="综合", source_name="Source B"),
        dict(fetched_at=start - timedelta(days=6, microseconds=1), source_category="综合"),
    ])
    stats = crud.get_stats()
    assert stats["total_articles"] == 5
    assert stats["categories"] == {"科技": 2, "未分类": 1, "综合": 2}
    assert stats["sources_count"] == 2
    assert stats["ai_processed_count"] == 1
    assert stats["multi_source_articles"] == 1
    assert stats["official_confirmed_articles"] == 1
    assert stats["latest_fetch"] == "2026-09-08T15:59:59.999999Z"
    assert stats["today"] == {"date": "2026-09-08", "total": 2, "ai_processed": 1}
    assert stats["yesterday"] == {"date": "2026-09-07", "total": 1, "ai_processed": 0}
    assert stats["daily"] == [stats["today"], stats["yesterday"],
                              {"date": "2026-09-02", "total": 1, "ai_processed": 0}]


def test_future_articles_do_not_displace_recent_days(stats_db):
    _, sessions = stats_db
    add_articles(sessions, [
        dict(fetched_at=datetime(2026, 9, 1, 16)),
        dict(fetched_at=datetime(2026, 9, 8, 16)),
    ])
    stats = crud.get_stats()
    assert stats["total_articles"] == 2
    assert stats["daily"] == [{"date": "2026-09-02", "total": 1, "ai_processed": 0}]
    assert stats["today"] is None
    assert stats["yesterday"] is None


def test_stats_respects_daylight_saving_day_boundaries(stats_db):
    _, sessions = stats_db
    tz = ZoneInfo("America/New_York")
    # November 1 has 25 hours in this time zone in 2026.
    add_articles(sessions, [
        dict(fetched_at=datetime(2026, 11, 1, 4)),
        dict(fetched_at=datetime(2026, 11, 2, 4, 59, 59, 999999)),
        dict(fetched_at=datetime(2026, 11, 2, 5)),
    ])
    with patch.object(crud, "app_timezone", return_value=tz), patch(
        "app.time_utils.app_timezone", return_value=tz
    ), patch.object(crud, "datetime") as clock:
        clock.now.return_value = datetime(2026, 11, 2, 12, tzinfo=tz)
        stats = crud.get_stats()
    assert stats["today"] == {"date": "2026-11-02", "total": 1, "ai_processed": 0}
    assert stats["yesterday"] == {"date": "2026-11-01", "total": 2, "ai_processed": 0}


def test_stats_does_not_fetch_article_bodies(stats_db):
    engine, sessions = stats_db
    add_articles(sessions, [dict(fetched_at=datetime(2026, 9, 8), raw_content="x" * 100_000)])
    statements = []

    def record_sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_sql)
    try:
        assert crud.get_stats()["total_articles"] == 1
    finally:
        event.remove(engine, "before_cursor_execute", record_sql)
    assert statements
    for statement in statements:
        for field in ("raw_content", "raw_summary", "ai_summary", "title"):
            assert field not in statement.lower()
