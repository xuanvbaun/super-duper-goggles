"""API 路由定义"""

import hmac
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from . import collector, crud
from .ai_processor import get_ai_provider, process_unprocessed_articles
from .config import get_config
from .daily_report import generate_yesterday_html
from .rule_engine import score_articles
from .time_utils import iso_utc
from .verification import cluster_recent_articles, parse_sources

router = APIRouter(prefix="/api")


def _tags(value: str | None, fallback: str | None = None) -> list[str]:
    tags = [item.strip() for item in (value or "").split(",") if item.strip()][:5]
    return tags or ([fallback] if fallback else [])


def _safe_article_url(value: str) -> str:
    parsed = urlparse(value or "")
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    configured = get_config().security.admin_token
    if not configured:
        raise HTTPException(
            status_code=503, detail="管理员接口未启用，请先设置 ADMIN_TOKEN"
        )
    if not x_admin_token or not hmac.compare_digest(x_admin_token, configured):
        raise HTTPException(status_code=401, detail="管理员令牌无效")


# ---- 新闻 ----
@router.get("/news")
def list_news(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    category: str | None = None,
    search: str | None = None,
    sort_by: str = "priority",
    date: str | None = None,  # "today" | "yesterday" | "2025-06-01"
):
    """获取分页新闻列表。支持 ?date=today 过滤今日新闻。"""
    articles, total = crud.list_articles(
        page=page,
        size=size,
        category=category,
        search=search,
        sort_by=sort_by,
        date_filter=date,
    )
    items = []
    for a in articles:
        items.append(
            {
                "id": a.id,
                "title": a.title,
                "url": _safe_article_url(a.url),
                "source_name": a.source_name,
                "source_category": a.source_category,
                "ai_summary": a.ai_summary,
                "raw_summary": a.raw_summary,  # fallback 显示原文
                "ai_category": a.ai_category,
                # 标签：优先用 AI 标签（过滤无效项），否则用源分类
                "ai_tags": _tags(a.ai_tags, a.source_category),
                "rule_score": a.rule_score,
                "event_id": a.event_id,
                "corroboration_count": a.corroboration_count or 1,
                "corroborating_sources": parse_sources(a.corroborating_sources),
                "verification_status": a.verification_status or "single_source",
                "official_confirmed": bool(a.official_confirmed),
                "published_at": iso_utc(a.published_at),
                "fetched_at": iso_utc(a.fetched_at),
                "ai_processed": a.ai_processed,
            }
        )
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size if size > 0 else 0,
    }


@router.get("/news/{article_id}")
def get_news_detail(article_id: str):
    """获取新闻详情。"""
    article = crud.get_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="新闻不存在或已过期")
    return {
        "id": article.id,
        "title": article.title,
        "url": _safe_article_url(article.url),
        "source_name": article.source_name,
        "source_category": article.source_category,
        "raw_summary": article.raw_summary,
        "ai_summary": article.ai_summary,
        "ai_category": article.ai_category,
        "ai_tags": _tags(article.ai_tags, article.source_category),
        "source_credibility": article.source_credibility,
        "rule_score": article.rule_score,
        "event_id": article.event_id,
        "corroboration_count": article.corroboration_count or 1,
        "corroborating_sources": parse_sources(article.corroborating_sources),
        "verification_status": article.verification_status or "single_source",
        "official_confirmed": bool(article.official_confirmed),
        "published_at": iso_utc(article.published_at),
        "fetched_at": iso_utc(article.fetched_at),
    }


# ---- 统计 ----
@router.get("/stats")
def get_stats():
    """获取系统统计数据。"""
    return crud.get_stats()


# ---- 源管理 ----
@router.get("/sources")
def list_sources():
    """获取 RSS 源列表及状态。"""
    return collector.get_sources_status()


# ---- 昨日日报（HTML 报纸页面）----
@router.get("/daily/yesterday", response_model=None)
def get_yesterday_daily():
    """获取昨日新闻的 HTML 报纸页面（浏览器打开后可 Print→另存PDF）。"""
    html = generate_yesterday_html()
    if html is None:
        raise HTTPException(status_code=404, detail="昨日无新闻")
    from fastapi.responses import HTMLResponse

    return HTMLResponse(content=html)


# ---- 手动触发 ----
@router.post("/admin/collect", dependencies=[Depends(require_admin)])
async def trigger_collection():
    """手动触发一次 RSS 采集。"""
    result = await collector.collect_all()
    return result


@router.post("/admin/process-ai", dependencies=[Depends(require_admin)])
async def trigger_ai_process():
    """手动触发一次 AI 处理。"""
    count = await process_unprocessed_articles(batch_size=get_config().ai.batch_size)
    clustered = cluster_recent_articles()
    scored = score_articles(force=True)
    return {"processed": count, "clustered": clustered, "scored": scored}


@router.post("/admin/score", dependencies=[Depends(require_admin)])
def trigger_scoring():
    """手动重跑事件聚类和评分。"""
    clustered = cluster_recent_articles()
    count = score_articles(force=True)
    return {"clustered": clustered, "scored": count}


# ---- 健康检查 ----
@router.get("/health")
async def health():
    """健康检查。"""
    ai_ok = await get_ai_provider().health_check()
    return {
        "status": "ok",
        "ai_available": ai_ok,
        "ai_mode": get_ai_provider().__class__.__name__,
    }
