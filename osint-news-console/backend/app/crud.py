"""数据库查询与统计。"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import case, func

from .database import get_session
from .models import NewsArticle
from .time_utils import app_timezone, iso_utc, local_day_bounds


def _resolve_date_filter(value: str, today: date | None = None) -> date:
    """把相对日期解析为业务时区日期；today 参数供测试和显式调用。"""
    today = today or datetime.now(app_timezone()).date()
    if value == "today":
        return today
    if value == "yesterday":
        return today - timedelta(days=1)
    return date.fromisoformat(value)


def _target_local_date(value: str) -> date:
    return _resolve_date_filter(value)


def _daily_summaries(
    daily: list[dict], today: date | None = None
) -> tuple[dict | None, dict | None]:
    """精确返回今天和昨天；缺失时不拿更早日期冒充。"""
    today = today or datetime.now(app_timezone()).date()
    by_date = {item["date"]: item for item in daily}
    return (
        by_date.get(today.isoformat()),
        by_date.get((today - timedelta(days=1)).isoformat()),
    )


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
    """在数据库内汇总，避免统计请求加载所有新闻正文与 ORM 对象。"""
    session = get_session()
    try:
        processed_count = func.sum(case((NewsArticle.ai_processed.is_(True), 1), else_=0))
        totals = session.query(
            func.count(NewsArticle.id).label("total"),
            processed_count.label("processed"),
            func.count(func.distinct(NewsArticle.source_name)).label("sources"),
            func.max(NewsArticle.fetched_at).label("latest"),
            func.sum(case((NewsArticle.corroboration_count >= 2, 1), else_=0)).label("multi"),
            func.sum(case((NewsArticle.official_confirmed.is_(True), 1), else_=0)).label("official"),
        ).one()
        # 空字符串与 NULL 均使用来源分类回退，保持原有展示语义。
        category = func.coalesce(
            func.nullif(NewsArticle.ai_category, ""),
            func.nullif(NewsArticle.source_category, ""),
            "未分类",
        )
        categories = dict(session.query(category, func.count(NewsArticle.id)).group_by(category).all())

        today = datetime.now(app_timezone()).date()
        # 分别计算业务时区的每日 UTC 边界，也适用于含夏令时的时区。
        days = [today - timedelta(days=offset) for offset in range(7)]
        bounds = [local_day_bounds(day) for day in days]
        day_key = case(*(
            (NewsArticle.fetched_at.between(start, end), day.isoformat())
            for day, (start, end) in zip(days, bounds)
        ))
        daily_rows = (
            session.query(
                day_key.label("day"),
                func.count(NewsArticle.id).label("total"),
                processed_count.label("processed"),
            )
            .filter(NewsArticle.fetched_at.between(bounds[-1][0], bounds[0][1]))
            .group_by(day_key)
            .order_by(day_key.desc())
            .all()
        )
        daily = [
            {"date": row.day, "total": row.total, "ai_processed": int(row.processed or 0)}
            for row in daily_rows
        ]
        today_data, yesterday_data = _daily_summaries(daily, today)
        return {
            "total_articles": totals.total,
            "ai_processed_count": int(totals.processed or 0),
            "categories": categories,
            "sources_count": totals.sources,
            "latest_fetch": iso_utc(totals.latest),
            "today": today_data,
            "yesterday": yesterday_data,
            "daily": daily,
            "multi_source_articles": int(totals.multi or 0),
            "official_confirmed_articles": int(totals.official or 0),
        }
    finally:
        session.close()
