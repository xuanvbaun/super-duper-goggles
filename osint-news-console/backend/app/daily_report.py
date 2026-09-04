"""HTML 报纸日报生成器

生成昨日新闻的 HTML 报纸页面。
纯 HTML，零外部依赖，手机/桌面通用。
浏览器打开后 Ctrl+P 即可另存为 PDF。
"""

import logging
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "daily"

NEWSPAPER_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>新闻日报 · {date_str}</title>
<style>
  :root {{
    --paper: #faf5eb;
    --text: #1a1a1a;
    --accent: #8b1a1a;
    --border: #d9ccb8;
    --muted: #8b7355;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: "SimSun", "STSong", "Noto Serif SC", "Microsoft YaHei", serif;
    font-size: 14px;
    line-height: 1.8;
    color: var(--text);
    background: #e8e0d5;
    max-width: 800px;
    margin: 0 auto;
    padding: 20px;
  }}
  @media print {{
    body {{ background: #fff; padding: 0; }}
    @page {{ size: A4; margin: 1.5cm 2cm; }}
  }}
  @media (max-width: 600px) {{
    body {{ padding: 12px; font-size: 15px; }}
    .header h1 {{ font-size: 24px; }}
    .article h2 {{ font-size: 16px; }}
    .article .summary {{ font-size: 14px; }}
    .article .meta {{ font-size: 11px; }}
  }}
  .header {{
    text-align: center;
    border-bottom: 3px double var(--accent);
    padding-bottom: 16px;
    margin-bottom: 28px;
  }}
  .header h1 {{
    font-size: 32px;
    font-weight: 900;
    letter-spacing: 3px;
    margin: 0 0 6px;
  }}
  .header .date {{
    font-size: 13px;
    color: #666;
    letter-spacing: 1px;
  }}
  .article {{
    border-bottom: 1px solid var(--border);
    padding: 16px 0;
  }}
  .article .meta {{
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
  }}
  .article h2 {{
    font-size: 18px;
    font-weight: 700;
    line-height: 1.4;
    margin-bottom: 8px;
  }}
  .article .summary {{
    font-size: 13px;
    color: #444;
    line-height: 1.75;
    white-space: pre-wrap;
  }}
  .article .tags {{
    margin-top: 8px;
    font-size: 10px;
    color: var(--accent);
  }}
  .article .source {{
    font-size: 9px;
    color: #999;
    margin-top: 4px;
    word-break: break-all;
  }}
  .score-high {{ color: #2d7d46; }}
  .score-mid  {{ color: #b8860b; }}
  .score-low  {{ color: var(--accent); }}
  .divider {{
    text-align: center;
    margin: 20px 0;
    color: var(--accent);
    font-size: 11px;
    letter-spacing: 10px;
  }}
  .footer {{
    margin-top: 36px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
    text-align: center;
    font-size: 10px;
    color: #999;
  }}
</style>
</head>
<body>

<div class="header">
  <h1>新闻控制台 · 日报</h1>
  <div class="date">{date_str}</div>
</div>

{articles_html}

<div class="footer">
  数据保留 7 天 · 生成于 {gen_time}<br>
  OSINT 新闻控制台 v1.0
</div>

</body>
</html>"""

ARTICLE_HTML = """<div class="article">
  <div class="meta">{source} · {category} · {score_text}</div>
  <h2>{title}</h2>
  <div class="summary">{summary}</div>
  <div class="tags">{tags}</div>
  <div class="link"><a href="{url}" target="_blank" rel="noopener noreferrer">阅读原文 →</a></div>
</div>
"""


def _weekday_cn(weekday: int) -> str:
    return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][weekday]


def _escape_text(value: object) -> str:
    """Escape untrusted RSS or AI text before inserting it into HTML."""
    return escape(str(value or ""), quote=True)


def _safe_http_url(value: object) -> str:
    """Return an escaped HTTP(S) URL, or a harmless placeholder."""
    raw_url = str(value or "").strip()
    try:
        parsed = urlsplit(raw_url)
    except ValueError:
        return "#"
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return "#"
    return escape(raw_url, quote=True)


def generate_yesterday_html() -> str | None:
    """生成昨日新闻的 HTML 报纸页面。"""
    from .database import get_session
    from .models import NewsArticle
    from sqlalchemy import func

    session = get_session()

    # 先查昨天，没有则回退到今天
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")

    try:
        articles = (
            session.query(NewsArticle)
            .filter(func.date(NewsArticle.fetched_at) == yesterday_str)
            .order_by(NewsArticle.published_at.desc().nullslast(), NewsArticle.id.desc())
            .all()
        )
    except Exception:
        session.close()
        raise

    if not articles:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            articles = (
                session.query(NewsArticle)
                .filter(func.date(NewsArticle.fetched_at) == today_str)
                .order_by(NewsArticle.published_at.desc().nullslast(), NewsArticle.id.desc())
                .all()
            )
            yesterday_str = today_str  # 用今天日期
        except Exception:
            session.close()
            raise

    session.close()

    if not articles:
        return None

    parts = []
    for i, a in enumerate(articles):
        score = a.rule_score or 0
        if score >= 60:
            score_text = f"可信度 {score}"
        elif score >= 30:
            score_text = f"可信度 {score}"
        else:
            score_text = f"可信度 {score}" if score else ""

        tags = ", ".join((a.ai_tags or "").split(",")[:5]) if a.ai_tags else ""

        # 完整内容：优先 ai_summary，否则 raw_summary
        summary = a.ai_summary or a.raw_summary or ""
        if not summary.strip() or len(summary) < 20:
            summary = a.raw_summary or f"原文: {a.url}"

        parts.append(ARTICLE_HTML.format(
            source=_escape_text(a.source_name),
            category=_escape_text(a.ai_category or a.source_category),
            score_text=_escape_text(score_text),
            title=_escape_text(a.title or "无标题"),
            summary=_escape_text(summary).replace("\n", "<br>"),
            tags=_escape_text(tags),
            url=_safe_http_url(a.url),
        ))

        if (i + 1) % 8 == 0 and i + 1 < len(articles):
            parts.append('<div class="divider">* * *</div>')

    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    date_display = f"{yesterday_str}（{_weekday_cn(yesterday.weekday())}）"

    html = NEWSPAPER_TEMPLATE.format(
        date_str=date_display,
        articles_html="\n".join(parts),
        gen_time=gen_time,
    )

    # 缓存
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = _CACHE_DIR / f"daily-{yesterday_str}.html"
    cache_path.write_text(html, encoding="utf-8")

    logger.info(f"日报 HTML: {cache_path}（{len(articles)} 篇）")
    return html
