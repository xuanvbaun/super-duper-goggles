"""API 路由定义"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from . import crud, collector
from .rule_engine import score_all_unscored, cleanup_old_articles
from .ai_processor import process_unprocessed_articles, get_ai_provider
from .daily_report import generate_yesterday_html

router = APIRouter(prefix="/api")


# ---- 新闻 ----
@router.get("/news")
def list_news(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    category: str | None = None,
    search: str | None = None,
    sort_by: str = "published_at",
    date: str | None = None,  # "today" | "yesterday" | "2025-06-01"
):
    """获取分页新闻列表。支持 ?date=today 过滤今日新闻。"""
    articles, total = crud.list_articles(
        page=page, size=size, category=category, search=search, sort_by=sort_by, date_filter=date
    )
    items = []
    for a in articles:
        items.append({
            "id": a.id,
            "title": a.title,
            "url": a.url,
            "source_name": a.source_name,
            "source_category": a.source_category,
            "ai_summary": a.ai_summary,
            "raw_summary": a.raw_summary,  # fallback 显示原文
            "ai_category": a.ai_category,
            # 标签：优先用 AI 标签（过滤无效项），否则用源分类
            "ai_tags": (
                [t for t in (a.ai_tags.split(",") if a.ai_tags else []) if t in ("综合","科技","安全","财经","国际","社会","法律","军事","其他","非中文")]
                or [a.source_category]
            ),
            "rule_score": a.rule_score,
            "published_at": a.published_at.isoformat() if a.published_at else None,
            "fetched_at": a.fetched_at.isoformat() if a.fetched_at else None,
            "ai_processed": a.ai_processed,
        })
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
        "url": article.url,
        "source_name": article.source_name,
        "source_category": article.source_category,
        "raw_summary": article.raw_summary,
        "ai_summary": article.ai_summary,
        "ai_category": article.ai_category,
        "ai_tags": [t for t in (article.ai_tags.split(",") if article.ai_tags else []) if t in ("综合","科技","安全","财经","国际","社会","法律","军事","其他","非中文")],
        "source_credibility": article.source_credibility,
        "rule_score": article.rule_score,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "fetched_at": article.fetched_at.isoformat() if article.fetched_at else None,
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
@router.post("/admin/collect")
async def trigger_collection():
    """手动触发一次 RSS 采集。"""
    result = await collector.collect_all()
    return result


@router.post("/admin/process-ai")
async def trigger_ai_process():
    """手动触发一次 AI 处理。"""
    count = await process_unprocessed_articles(batch_size=20)
    return {"processed": count}


@router.post("/admin/score")
def trigger_scoring():
    """手动触发一次可信度评分。"""
    count = score_all_unscored()
    return {"scored": count}


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
