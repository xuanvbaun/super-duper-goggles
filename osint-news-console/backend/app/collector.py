"""RSS 采集器 — 支持按来源配置采集频率和并发请求。"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from urllib.parse import urlparse

import feedparser
import httpx
import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .config import get_config, get_project_root
from .database import get_session
from .models import NewsArticle
from .time_utils import app_timezone, as_utc_naive, iso_utc, utc_now

logger = logging.getLogger(__name__)


def _load_sources() -> list[dict]:
    sources_path = get_project_root() / "sources.yaml"
    if not sources_path.exists():
        logger.warning("sources.yaml 未找到：%s", sources_path)
        return []
    with sources_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    return data.get("sources", [])


def _effective_interval(source: dict) -> int:
    return int(
        source.get("interval_minutes") or get_config().collector.interval_minutes
    )


def _safe_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _strip_html(text: str) -> str:
    clean = re.sub(r"<[^>]+>", "", text or "")
    clean = re.sub(r"\s+", " ", unescape(clean))
    return clean.strip()


def _clean_metadata_summary(text: str) -> str:
    if not text:
        return text
    if "Article URL:" in text and "Comments URL:" in text:
        return ""
    if text.strip().startswith("点击查看原文"):
        return ""
    if text.strip().startswith(("http://", "https://")):
        return ""
    if len(text.strip()) < 5:
        return ""
    return text


def _entry_published_at(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        try:
            return as_utc_naive(datetime(*parsed[:6], tzinfo=timezone.utc))
        except (TypeError, ValueError):
            pass
    return None


def _latest_entry_published_at(entries: list) -> datetime | None:
    published = [
        value for entry in entries if (value := _entry_published_at(entry)) is not None
    ]
    return max(published, default=None)


def _entry_source_name(source: dict, entry) -> str:
    """聚合源可保留原始媒体名，避免所有报道都显示成“Google 新闻”。"""
    if not source.get("use_entry_source", False):
        return source["name"]
    entry_source = entry.get("source") or {}
    source_title = _strip_html(str(entry_source.get("title", ""))).strip()
    return source_title[:200] or source["name"]


def _stale_after_hours(source: dict) -> float:
    configured = source.get("stale_after_hours")
    if configured is not None:
        return max(float(configured), 1.0)
    return max(24.0, _effective_interval(source) * 6 / 60)


def _freshness_status(
    source: dict, latest_published_at: datetime | None
) -> tuple[str, str | None]:
    if latest_published_at is None:
        return "unknown", "RSS 未提供可识别的发布时间"
    age = utc_now() - latest_published_at
    limit = timedelta(hours=_stale_after_hours(source))
    if age > limit:
        return (
            "stale",
            f"最新条目已超过 {round(age.total_seconds() / 3600, 1)} 小时未更新",
        )
    return "ok", None


def _insert_entries(source: dict, entries: list) -> int:
    name = source["name"]
    session = get_session()
    new_count = 0
    try:
        retention_cutoff = utc_now() - timedelta(
            days=get_config().cleanup.retention_days
        )
        max_entries = get_config().collector.max_entries_per_source
        for entry in entries[:max_entries]:
            article_url = str(entry.get("link", "")).strip()
            if not _safe_http_url(article_url):
                continue
            existing = (
                session.query(NewsArticle)
                .filter(NewsArticle.url == article_url)
                .first()
            )
            if existing:
                # 配置升级后同步来源属性，不要求用户删除旧数据库。
                existing.source_category = source.get(
                    "category", existing.source_category
                )
                existing.source_credibility = int(source.get("credibility", 3))
                existing.source_official = bool(source.get("official", False))
                continue

            published_at = _entry_published_at(entry)
            if published_at and published_at < retention_cutoff:
                continue
            raw_summary = entry.get("summary", "") or entry.get("description", "")
            raw_summary = _clean_metadata_summary(_strip_html(raw_summary))
            article = NewsArticle(
                title=_strip_html(entry.get("title", "无标题"))[:500] or "无标题",
                url=article_url,
                source_name=_entry_source_name(source, entry),
                source_category=source.get("category", "未分类"),
                source_credibility=int(source.get("credibility", 3)),
                source_official=bool(source.get("official", False)),
                raw_summary=raw_summary[:5000] if raw_summary else None,
                published_at=published_at,
                ai_processed=False,
            )
            session.add(article)
            new_count += 1
        session.commit()
        return new_count
    except Exception:
        session.rollback()
        logger.exception("[%s] 入库失败", name)
        return 0
    finally:
        session.close()


async def _fetch_single_source(
    source: dict,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
) -> int:
    name = source["name"]
    url = source["url"]
    if not _safe_http_url(url):
        _update_source_status(name, "error", "RSS URL 非法")
        return 0

    try:
        async with semaphore:
            response = await client.get(
                url,
                timeout=get_config().collector.request_timeout,
                follow_redirects=True,
                headers=_source_request_headers.get(name),
            )
            if response.status_code == 304:
                previous = _source_status.get(name, {})
                latest = previous.get("latest_published_at")
                status, error = _freshness_status(source, latest)
                _update_source_status(
                    name, status, error, latest_published_at=latest, http_status=304
                )
                return 0
            response.raise_for_status()
            cached_headers = {}
            if response.headers.get("etag"):
                cached_headers["If-None-Match"] = response.headers["etag"]
            if response.headers.get("last-modified"):
                cached_headers["If-Modified-Since"] = response.headers[
                    "last-modified"
                ]
            if cached_headers:
                _source_request_headers[name] = cached_headers
        feed = feedparser.parse(response.content)
        if feed.bozo:
            logger.warning("[%s] RSS 解析警告: %s", name, feed.bozo_exception)
        latest = _latest_entry_published_at(feed.entries)
        count = _insert_entries(source, feed.entries)
        status, error = _freshness_status(source, latest)
        _update_source_status(
            name,
            status,
            error,
            latest_published_at=latest,
            http_status=response.status_code,
        )
        if count:
            logger.info("[%s] 新增 %s 条", name, count)
        return count
    except Exception as exc:  # noqa: BLE001 - 单个第三方源失败不能中断整轮采集
        logger.error("[%s] 请求失败: %s", name, exc)
        _update_source_status(name, "error", str(exc)[:500])
        return 0


_source_status: dict[str, dict] = {}
_source_request_headers: dict[str, dict[str, str]] = {}


def _update_source_status(
    name: str,
    status: str,
    error: str | None,
    *,
    latest_published_at: datetime | None = None,
    http_status: int | None = None,
) -> None:
    previous = _source_status.get(name, {})
    _source_status[name] = {
        "last_status": status,
        "last_error": error,
        "last_fetched_at": utc_now(),
        "latest_published_at": latest_published_at
        if latest_published_at is not None
        else previous.get("latest_published_at"),
        "last_http_status": http_status,
    }


def get_sources_status() -> list[dict]:
    result = []
    for source in _load_sources():
        status = _source_status.get(source["name"], {})
        result.append(
            {
                "name": source["name"],
                "url": source["url"],
                "category": source.get("category", ""),
                "credibility": source.get("credibility", 3),
                "official": source.get("official", False),
                "enabled": source.get("enabled", True),
                "interval_minutes": _effective_interval(source),
                "last_status": status.get("last_status"),
                "last_error": status.get("last_error"),
                "last_fetched_at": iso_utc(status.get("last_fetched_at")),
                "latest_published_at": iso_utc(
                    status.get("latest_published_at")
                ),
                "stale_after_hours": _stale_after_hours(source),
                "last_http_status": status.get("last_http_status"),
            }
        )
    return result


async def _collect_sources(sources: list[dict]) -> dict:
    if not sources:
        return {"total_sources": 0, "total_new": 0}
    config = get_config().collector
    semaphore = asyncio.Semaphore(config.max_concurrency)
    headers = {"User-Agent": config.user_agent}
    async with httpx.AsyncClient(headers=headers) as client:
        counts = await asyncio.gather(
            *(_fetch_single_source(source, client, semaphore) for source in sources)
        )
    result = {"total_sources": len(sources), "total_new": sum(counts)}
    if result["total_new"]:
        # 新文章入库后立即更新事件标记；AI 摘要可在后续批次慢慢补齐。
        from .rule_engine import score_articles
        from .verification import cluster_recent_articles

        cluster_recent_articles()
        score_articles(force=True)
    logger.info("采集完成：%s", result)
    return result


async def collect_all() -> dict:
    enabled = [source for source in _load_sources() if source.get("enabled", True)]
    return await _collect_sources(enabled)


async def collect_interval(interval_minutes: int) -> dict:
    enabled = [
        source
        for source in _load_sources()
        if source.get("enabled", True)
        and _effective_interval(source) == interval_minutes
    ]
    return await _collect_sources(enabled)


_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> None:
    """每个采集频率建立独立任务；首次采集由应用 lifespan 显式执行。"""
    global _scheduler
    if _scheduler is not None:
        return

    enabled = [source for source in _load_sources() if source.get("enabled", True)]
    intervals = sorted({_effective_interval(source) for source in enabled})
    _scheduler = AsyncIOScheduler(timezone=get_config().timezone)
    for interval in intervals:
        _scheduler.add_job(
            collect_interval,
            "interval",
            minutes=interval,
            args=[interval],
            id=f"rss_collection_{interval}m",
            name=f"RSS 采集（{interval}分钟）",
            next_run_time=datetime.now(app_timezone()) + timedelta(minutes=interval),
            max_instances=1,
            coalesce=True,
        )
    _scheduler.start()
    logger.info("RSS 调度器已启动，采集频率：%s", intervals)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("RSS 采集调度器已停止")
