"""可解释的优先级评分与数据清理。

分数表示“来源、交叉报道、时效和内容完整度”的综合程度，不代表事实真伪。
"""

import logging
from datetime import timedelta

from .config import get_config
from .database import get_session
from .models import NewsArticle
from .time_utils import as_utc_naive, utc_now

logger = logging.getLogger(__name__)


def calculate_credibility_score(article: NewsArticle) -> float:
    config = get_config().rule_engine
    source_score = min(100.0, max(0.0, article.source_credibility / 5.0 * 100))

    published = as_utc_naive(article.published_at)
    if published:
        age_hours = max(0.0, (utc_now() - published).total_seconds() / 3600)
        if age_hours <= 24:
            freshness_score = 100.0
        elif age_hours >= 168:
            freshness_score = 0.0
        else:
            freshness_score = 100.0 * (1.0 - (age_hours - 24) / 144)
    else:
        freshness_score = 50.0

    completeness_score = 0.0
    if article.raw_summary:
        completeness_score += 45
    if article.ai_processed and article.ai_summary:
        completeness_score += 55

    source_count = max(1, article.corroboration_count or 1)
    if source_count >= 3:
        corroboration_score = 100.0
    elif source_count == 2:
        corroboration_score = 75.0
    else:
        corroboration_score = 20.0

    score = (
        source_score * config.source_weight
        + corroboration_score * config.corroboration_weight
        + freshness_score * config.freshness_weight
        + completeness_score * config.completeness_weight
    )
    if article.official_confirmed:
        score += config.official_bonus
    return round(min(100.0, max(0.0, score)), 1)


def score_articles(force: bool = True) -> int:
    """重算评分。AI处理或事件聚类变化后必须 force=True。"""
    session = get_session()
    count = 0
    try:
        query = session.query(NewsArticle)
        if not force:
            query = query.filter(NewsArticle.rule_score.is_(None))
        for article in query.all():
            article.rule_score = calculate_credibility_score(article)
            count += 1
        session.commit()
        return count
    except Exception:
        session.rollback()
        logger.exception("评分失败")
        return 0
    finally:
        session.close()


def score_all_unscored() -> int:
    """保留旧调用兼容；新流程通常使用 score_articles(force=True)。"""
    return score_articles(force=False)


def cleanup_old_articles() -> int:
    retention_days = get_config().cleanup.retention_days
    cutoff = utc_now() - timedelta(days=retention_days)
    session = get_session()
    try:
        deleted = (
            session.query(NewsArticle)
            .filter(NewsArticle.fetched_at < cutoff)
            .delete(synchronize_session=False)
        )
        session.commit()
        if deleted:
            logger.info("%s 天清理：删除 %s 条过期新闻", retention_days, deleted)
        return deleted
    except Exception:
        session.rollback()
        logger.exception("清理失败")
        return 0
    finally:
        session.close()
