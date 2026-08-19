"""数据库 CRUD 操作"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func

from .database import get_session
from .models import NewsArticle

logger = logging.getLogger(__name__)


def list_articles(
    page: int = 1,
    size: int = 20,
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "published_at",
    date_filter: Optional[str] = None,  # "today" | "yesterday" | "2025-06-01"
) -> tuple[list[NewsArticle], int]:
    """分页获取新闻列表，返回 (文章列表, 总数)。"""
    session = get_session()
    try:
        query = session.query(NewsArticle)

        if category:
            # 优先 AI 分类，未处理时用源分类
            query = query.filter(
                (NewsArticle.ai_category == category) |
                ((NewsArticle.ai_category.is_(None)) & (NewsArticle.source_category == category))
            )
        if search:
            like_pattern = f"%{search}%"
            query = query.filter(
                NewsArticle.title.ilike(like_pattern)
                | NewsArticle.ai_summary.ilike(like_pattern)
                | NewsArticle.ai_tags.ilike(like_pattern)
            )
        if date_filter:
            from datetime import date, timedelta
            if date_filter == "today":
                target = date.today()
            elif date_filter == "yesterday":
                target = date.today() - timedelta(days=1)
            else:
                target = date.fromisoformat(date_filter)
            query = query.filter(func.date(NewsArticle.fetched_at) == target.isoformat())

        total = query.count()

        # 排序：发布时间降序（无发布时间的排最后），同时间按 id 降序
        sort_col = getattr(NewsArticle, sort_by, NewsArticle.published_at)
        articles = (
            query.order_by(sort_col.desc().nullslast(), NewsArticle.id.desc())
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )
        return articles, total
    finally:
        session.close()


def get_article(article_id: str) -> NewsArticle | None:
    """获取单条新闻详情。"""
    session = get_session()
    try:
        return session.query(NewsArticle).filter(NewsArticle.id == article_id).first()
    finally:
        session.close()


def get_stats() -> dict:
    """获取统计信息（含每日明细）。"""
    session = get_session()
    try:
        total = session.query(func.count(NewsArticle.id)).scalar() or 0
        ai_processed = (
            session.query(func.count(NewsArticle.id))
            .filter(NewsArticle.ai_processed == True)  # noqa: E712
            .scalar()
            or 0
        )
        # 各类别数量
        cat_rows = (
            session.query(
                NewsArticle.ai_category,
                func.count(NewsArticle.id),
            )
            .group_by(NewsArticle.ai_category)
            .all()
        )
        categories = {row[0] or "未分类": row[1] for row in cat_rows}

        # 源数量
        sources_count = (
            session.query(func.count(func.distinct(NewsArticle.source_name))).scalar() or 0
        )

        # 最近采集时间
        latest = (
            session.query(NewsArticle.fetched_at)
            .order_by(NewsArticle.fetched_at.desc())
            .first()
        )
        latest_fetch = latest[0] if latest else None

        # ── 每日统计（近7天）──
        from sqlalchemy import case
        # SQLite 用 DATE() 函数提取日期部分（兼容文本格式的 datetime）
        day_col = func.date(NewsArticle.fetched_at).label("day")
        daily_rows = (
            session.query(
                day_col,
                func.count(NewsArticle.id).label("total"),
                func.sum(
                    case((NewsArticle.ai_processed == True, 1), else_=0)  # noqa: E712
                ).label("processed"),
            )
            .group_by(func.date(NewsArticle.fetched_at))
            .order_by(func.date(NewsArticle.fetched_at).desc())
            .limit(7)
            .all()
        )
        daily = [
            {
                "date": str(row.day),
                "total": row.total,
                "ai_processed": int(row.processed or 0),
            }
            for row in daily_rows
        ]

        # 今日 / 昨日摘要
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_data = next((d for d in daily if d["date"] == today_str), None)
        yesterday_data = daily[1] if len(daily) > 1 and daily[0]["date"] == today_str else (daily[0] if len(daily) > 0 and daily[0]["date"] != today_str else None)

        return {
            "total_articles": total,
            "ai_processed_count": ai_processed,
            "categories": categories,
            "sources_count": sources_count,
            "latest_fetch": latest_fetch.isoformat() if latest_fetch else None,
            "today": today_data,
            "yesterday": yesterday_data,
            "daily": daily,
        }
    finally:
        session.close()
