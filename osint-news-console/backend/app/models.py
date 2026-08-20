"""SQLAlchemy ORM 模型"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base
from .time_utils import utc_now


def _now_utc() -> datetime:
    return utc_now()


def _new_uuid() -> str:
    return uuid.uuid4().hex[:16]


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_uuid)
    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    source_category: Mapped[str] = mapped_column(
        String(50), nullable=True, default="未分类"
    )

    # 原始内容
    raw_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # AI 处理结果
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ai_tags: Mapped[str | None] = mapped_column(String(500), nullable=True)  # 逗号分隔

    # 可信度
    source_credibility: Mapped[int] = mapped_column(Integer, default=3)
    source_official: Mapped[bool] = mapped_column(Boolean, default=False)
    rule_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 同事件聚类与交叉验证
    event_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    corroboration_count: Mapped[int] = mapped_column(Integer, default=1)
    corroborating_sources: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(32), default="single_source", index=True
    )
    official_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    # 时间戳
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, index=True
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=_now_utc, index=True)

    # 状态
    ai_processed: Mapped[bool] = mapped_column(default=False)

    # 复合索引
    __table_args__ = (
        Index("idx_category_processed", "source_category", "ai_processed"),
        Index("idx_published_fetched", "published_at", "fetched_at"),
    )

    def __repr__(self) -> str:
        return f"<NewsArticle(id={self.id}, title={self.title[:40]}...)>"
