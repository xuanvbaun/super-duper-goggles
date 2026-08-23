"""Pydantic 请求/响应模型"""

from datetime import datetime


# ---- 新闻 ----
class NewsItem:
    """新闻列表项（简化，用于序列化）"""

    id: str
    title: str
    url: str
    source_name: str
    source_category: str
    ai_summary: str | None
    ai_category: str | None
    ai_tags: list[str]
    rule_score: float | None
    published_at: datetime | None
    fetched_at: datetime
    ai_processed: bool

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class NewsListResponse:
    """分页新闻列表"""

    items: list[dict]
    total: int
    page: int
    size: int
    pages: int

    def __init__(self, items, total, page, size):
        self.items = items
        self.total = total
        self.page = page
        self.size = size
        self.pages = (total + size - 1) // size if size > 0 else 0


class NewsDetail:
    """新闻详情"""

    id: str
    title: str
    url: str
    source_name: str
    source_category: str
    raw_summary: str | None
    ai_summary: str | None
    ai_category: str | None
    ai_tags: list[str]
    source_credibility: int
    rule_score: float | None
    published_at: datetime | None
    fetched_at: datetime

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ---- 统计 ----
class StatsResponse:
    total_articles: int
    sources_count: int
    categories: dict[str, int]
    latest_fetch: datetime | None
    ai_processed_count: int

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ---- 采集源状态 ----
class SourceStatus:
    name: str
    url: str
    category: str
    credibility: int
    enabled: bool
    last_status: str | None  # "ok" / "stale" / "unknown" / "error"
    last_error: str | None
    last_fetched_at: datetime | None
    latest_published_at: datetime | None
    stale_after_hours: float
    last_http_status: int | None

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
