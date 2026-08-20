"""数据库查询与统计。"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import case

from .database import get_session
from .models import NewsArticle
from .time_utils import app_timezone, as_local, iso_utc, local_day_bounds


def _target_local_date(value: str) -> date:
    today = datetime.now(app_timezone()).date()
    if value == "today":
        return today
    if value == "yesterday":
        return today - timedelta(days=1)
    return date.fromisoformat(value)


def list_articles(
    page: int = 1,
    size: int = 20,
    category: str | None = None,
    search: str | None = None,
    sort_by: str = "priority",
    date_filter: str | None = None,
) -> tuple[list[NewsArticle], int]:
    session = get_session()
    try:
        query = session.query(NewsArticle)
        if category:
            query = query.filter(
                (NewsArticle.ai_category == category)
                | (
                    NewsArticle.ai_category.is_(None)
                    & (NewsArticle.source_category == category)
                )
            )
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                NewsArticle.title.ilike(pattern)
                | NewsArticle.ai_summary.ilike(pattern)
                | NewsArticle.raw_summary.ilike(pattern)
                | NewsArticle.ai_tags.ilike(pattern)
            )
        if date_filter:
            start, end = local_day_bounds(_target_local_date(date_filter))
            query = query.filter(NewsArticle.fetched_at.between(start, end))

        total = query.count()
        if sort_by == "priority":
            verification_rank = case(
                (NewsArticle.verification_status == "official_confirmed", 3),
                (NewsArticle.verification_status == "multi_source", 2),
                else_=1,
            )
            order = (
                verification_rank.desc(),
                NewsArticle.corroboration_count.desc(),
                NewsArticle.rule_score.desc().nullslast(),
                NewsArticle.published_at.desc().nullslast(),
            )
        else:
            allowed = {
                "published_at": NewsArticle.published_at,
                "fetched_at": NewsArticle.fetched_at,
                "rule_score": NewsArticle.rule_score,
            }
            order = (allowed.get(sort_by, NewsArticle.published_at).desc().nullslast(),)

        articles = (
            query.order_by(*order, NewsArticle.id.desc())
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )
        return articles, total
    finally:
        session.close()


def get_article(article_id: str) -> NewsArticle | None:
    session = get_session()
    try:
        return session.query(NewsArticle).filter(NewsArticle.id == article_id).first()
    finally:
        session.close()


def get_stats() -> dict:
    session = get_session()
    try:
        articles = session.query(NewsArticle).all()
        total = len(articles)
        categories = Counter(
            article.ai_category or article.source_category or "未分类"
            for article in articles
        )
        sources_count = len({article.source_name for article in articles})
        ai_processed = sum(1 for article in articles if article.ai_processed)
        latest = max((article.fetched_at for article in articles), default=None)

        today = datetime.now(app_timezone()).date()
        seven_days_ago, _ = local_day_bounds(today - timedelta(days=6))
        daily_map: dict[str, dict[str, int]] = defaultdict(
            lambda: {"total": 0, "ai_processed": 0}
        )
        for article in articles:
            if article.fetched_at < seven_days_ago:
                continue
            local_value = as_local(article.fetched_at)
            if not local_value:
                continue
            key = local_value.date().isoformat()
            daily_map[key]["total"] += 1
            daily_map[key]["ai_processed"] += int(article.ai_processed)

        daily = [
            {"date": key, **daily_map[key]} for key in sorted(daily_map, reverse=True)
        ][:7]
        today_key = today.isoformat()
        yesterday_key = (today - timedelta(days=1)).isoformat()
        return {
            "total_articles": total,
            "ai_processed_count": ai_processed,
            "categories": dict(categories),
            "sources_count": sources_count,
            "latest_fetch": iso_utc(latest),
            "today": next((item for item in daily if item["date"] == today_key), None),
            "yesterday": next(
                (item for item in daily if item["date"] == yesterday_key), None
            ),
            "daily": daily,
            "multi_source_articles": sum(
                1 for article in articles if (article.corroboration_count or 1) >= 2
            ),
            "official_confirmed_articles": sum(
                1 for article in articles if article.official_confirmed
            ),
        }
    finally:
        session.close()
