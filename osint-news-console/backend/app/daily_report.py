"""安全生成昨日新闻 HTML 日报。"""

import logging
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

from .time_utils import app_timezone, local_day_bounds
from .verification import parse_sources

logger = logging.getLogger(__name__)
_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "daily"

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>新闻日报 · {date}</title>
<style>
:root{{--paper:#faf5eb;--text:#1a1a1a;--accent:#8b1a1a;--border:#d9ccb8;--muted:#8b7355}}
*{{box-sizing:border-box}} body{{font-family:"SimSun","Noto Serif SC",serif;color:var(--text);
background:#e8e0d5;max-width:820px;margin:auto;padding:20px;line-height:1.75}}
main{{background:var(--paper);padding:26px}} header{{text-align:center;border-bottom:3px double var(--accent);
margin-bottom:20px}} h1{{letter-spacing:3px}} article{{border-bottom:1px solid var(--border);padding:16px 0}}
h2{{font-size:18px;line-height:1.45}} .meta,.sources{{font-size:11px;color:var(--muted)}}
.summary{{font-size:14px;white-space:pre-wrap}} .badge{{display:inline-block;border:1px solid var(--accent);
color:var(--accent);padding:1px 6px;margin-left:6px}} a{{color:var(--accent)}} footer{{text-align:center;
font-size:10px;color:#999;margin-top:30px}}
@media(max-width:600px){{body{{padding:0}}main{{padding:16px}}h1{{font-size:24px}}}}
@media print{{body{{background:#fff;padding:0}}main{{padding:0}}@page{{size:A4;margin:1.5cm}}}}
</style></head><body><main>
<header><h1>新闻控制台 · 日报</h1><p>{date}</p></header>
{articles}
<footer>交叉来源仅表示多家媒体报道，不等同于事实真伪结论。<br>
数据保留 {retention_days} 天 · 生成于 {generated}</footer>
</main></body></html>"""

ARTICLE = """<article>
<div class="meta">{source} · {category} · 评分 {score} {badge}</div>
<h2>{title}</h2><div class="summary">{summary}</div>
<div class="sources">{sources}</div><a href="{url}" target="_blank" rel="noopener noreferrer">阅读原文 →</a>
</article>"""


def _safe_http_url(value: object) -> str:
    """只允许完整 HTTP(S) 地址，并按 HTML 属性上下文转义。"""
    raw_url = str(value or "").strip()
    try:
        parsed = urlsplit(raw_url)
    except ValueError:
        return "#"
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return "#"
    return escape(raw_url, quote=True)


def _verification_badge(status: str, count: int) -> str:
    if status == "official_confirmed":
        return '<span class="badge">含官方来源</span>'
    if status == "multi_source":
        return f'<span class="badge">{count}个来源交叉报道</span>'
    return '<span class="badge">单一来源</span>'


def _query_for_date(target):
    from .database import get_session
    from .models import NewsArticle

    start, end = local_day_bounds(target)
    session = get_session()
    try:
        return (
            session.query(NewsArticle)
            .filter(NewsArticle.fetched_at.between(start, end))
            .order_by(
                NewsArticle.official_confirmed.desc(),
                NewsArticle.corroboration_count.desc(),
                NewsArticle.rule_score.desc().nullslast(),
                NewsArticle.published_at.desc().nullslast(),
            )
            .all()
        )
    finally:
        session.close()


def generate_yesterday_html() -> str | None:
    from .config import get_config

    local_now = datetime.now(app_timezone())
    target = local_now.date() - timedelta(days=1)
    articles = _query_for_date(target)
    if not articles:
        target = local_now.date()
        articles = _query_for_date(target)
    if not articles:
        return None

    parts = []
    for article in articles:
        summary = (
            article.ai_summary or article.raw_summary or "RSS未提供摘要，请查看原文。"
        )
        sources = parse_sources(article.corroborating_sources)
        source_text = (
            "交叉来源：" + "、".join(sources)
            if len(sources) > 1
            else "当前仅有单一来源"
        )
        parts.append(
            ARTICLE.format(
                source=escape(article.source_name or ""),
                category=escape(article.ai_category or article.source_category or ""),
                score=escape(str(article.rule_score or "—")),
                badge=_verification_badge(
                    article.verification_status, article.corroboration_count or 1
                ),
                title=escape(article.title or "无标题"),
                summary=escape(summary).replace("\n", "<br>"),
                sources=escape(source_text),
                url=_safe_http_url(article.url),
            )
        )

    config = get_config()
    html = TEMPLATE.format(
        date=escape(target.isoformat()),
        articles="\n".join(parts),
        retention_days=config.cleanup.retention_days,
        generated=local_now.strftime("%Y-%m-%d %H:%M"),
    )
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _CACHE_DIR / f"daily-{target.isoformat()}.html"
    path.write_text(html, encoding="utf-8")
    logger.info("日报 HTML: %s（%s 篇）", path, len(articles))
    return html
