"""RSS 采集器 — feedparser + APScheduler 定时任务"""

import hashlib
import logging
from datetime import datetime, timezone

import feedparser
import httpx
import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pathlib import Path

from .config import get_config
from .database import get_session
from .models import NewsArticle

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent.parent  # D:\xd\


def _load_sources() -> list[dict]:
    """加载 sources.yaml 中的 RSS 源列表。"""
    sources_path = _BASE_DIR / "sources.yaml"
    if not sources_path.exists():
        logger.warning("sources.yaml 未找到，使用空源列表")
        return []
    with open(sources_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("sources", [])


def _url_hash(url: str) -> str:
    """对 URL 做 MD5 短哈希，用于去重。"""
    return hashlib.md5(url.encode("utf-8")).hexdigest()


async def _fetch_single_source(source: dict, client: httpx.AsyncClient) -> int:
    """采集单个 RSS 源，返回新增条目数。"""
    name = source["name"]
    url = source["url"]
    category = source.get("category", "未分类")
    credibility = source.get("credibility", 3)
    timeout = get_config().collector.request_timeout

    logger.info(f"采集 [{name}] — {url}")

    try:
        response = await client.get(url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"[{name}] 请求失败: {e}")
        _update_source_status(name, "error", str(e))
        return 0

    feed = feedparser.parse(response.text)
    if feed.bozo:
        logger.warning(f"[{name}] RSS 解析警告: {feed.bozo_exception}")

    new_count = 0
    session = get_session()

    try:
        for entry in feed.entries:
            article_url = entry.get("link", "")
            if not article_url:
                continue

            # 去重检查
            existing = session.query(NewsArticle).filter(
                NewsArticle.url == article_url
            ).first()
            if existing:
                continue

            # 提取发布时间
            published_at = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass
            if published_at is None:
                published_at = datetime.now(timezone.utc)

            # 提取内容摘要
            raw_summary = entry.get("summary", "") or entry.get("description", "")
            raw_summary = _strip_html(raw_summary)
            # 清理无意义 RSS 元数据（如 Hacker News 的 Article URL / Points 格式）
            raw_summary = _clean_metadata_summary(raw_summary, article_url)

            article = NewsArticle(
                title=entry.get("title", "无标题")[:500],
                url=article_url,
                source_name=name,
                source_category=category,
                source_credibility=credibility,
                raw_summary=raw_summary[:5000] if raw_summary else None,
                published_at=published_at,
                ai_processed=False,
            )
            session.add(article)
            new_count += 1

        session.commit()
        _update_source_status(name, "ok", None)

    except Exception as e:
        session.rollback()
        logger.error(f"[{name}] 入库失败: {e}")
        _update_source_status(name, "error", str(e))
    finally:
        session.close()

    if new_count > 0:
        logger.info(f"[{name}] 新增 {new_count} 条")
    return new_count


def _strip_html(text: str) -> str:
    """简单去除 HTML 标签。"""
    import re
    clean = re.sub(r"<[^>]+>", "", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def _clean_metadata_summary(text: str, article_url: str) -> str:
    """清理无意义的 RSS 元数据摘要。"""
    if not text:
        return text
    # Hacker News via hnrss.org: Article URL / Comments URL / Points
    if "Article URL:" in text and "Comments URL:" in text:
        return ""
    # InfoQ / IT之家 等站的「点击查看原文」提示
    if text.strip().startswith("点击查看原文"):
        return ""
    # 纯链接格式
    if text.strip().startswith("http://") or text.strip().startswith("https://"):
        return ""
    # 过短无意义摘要（<5字）
    if len(text.strip()) < 5:
        return ""
    return text


# ---- 源状态缓存（内存）----
_source_status: dict[str, dict] = {}


def _update_source_status(name: str, status: str, error: str | None):
    _source_status[name] = {
        "last_status": status,
        "last_error": error,
        "last_fetched_at": datetime.now(timezone.utc),
    }


def get_sources_status() -> list[dict]:
    """获取所有源的状态信息。"""
    sources = _load_sources()
    result = []
    for s in sources:
        status = _source_status.get(s["name"], {})
        result.append({
            "name": s["name"],
            "url": s["url"],
            "category": s.get("category", ""),
            "credibility": s.get("credibility", 3),
            "enabled": s.get("enabled", True),
            "last_status": status.get("last_status"),
            "last_error": status.get("last_error"),
            "last_fetched_at": status.get("last_fetched_at"),
        })
    return result


async def collect_all() -> dict:
    """采集所有启用的 RSS 源，返回统计结果。"""
    sources = _load_sources()
    enabled = [s for s in sources if s.get("enabled", True)]
    if not enabled:
        logger.info("无启用的 RSS 源")
        return {"total_sources": 0, "total_new": 0}

    config = get_config()
    headers = {"User-Agent": config.collector.user_agent}
    total_new = 0

    async with httpx.AsyncClient(headers=headers) as client:
        for source in enabled:
            try:
                count = await _fetch_single_source(source, client)
                total_new += count
            except Exception as e:
                logger.error(f"采集源 [{source['name']}] 异常: {e}")

    logger.info(f"采集完成：{len(enabled)} 个源，共新增 {total_new} 条")
    return {"total_sources": len(enabled), "total_new": total_new}


# ---- APScheduler ----
_scheduler: AsyncIOScheduler | None = None


def start_scheduler():
    """启动定时采集任务。"""
    global _scheduler
    if _scheduler is not None:
        return

    config = get_config()
    interval = config.collector.interval_minutes

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        collect_all,
        "interval",
        minutes=interval,
        id="rss_collection",
        name="RSS 定时采集",
        next_run_time=None,  # 启动后立即执行一次
    )
    _scheduler.start()
    logger.info(f"RSS 采集调度器已启动（每 {interval} 分钟）")


def stop_scheduler():
    """停止定时采集任务。"""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("RSS 采集调度器已停止")
