"""规则引擎 — 可信度评分 + 7 天数据自动清理"""

import logging
from datetime import datetime, timedelta, timezone

from .config import get_config
from .database import get_session
from .models import NewsArticle

logger = logging.getLogger(__name__)


def calculate_credibility_score(article: NewsArticle) -> float:
    """计算单条新闻的可信度评分 (0~100)。

    公式: source_credibility(60%) + freshness(20%) + completeness(20%)
    """
    config = get_config().rule_engine

    # 源可信度分（0-5 → 0-100）
    source_score = (article.source_credibility / 5.0) * 100

    # 时效性分（24h 内 = 100，超过 7 天 = 0，线性衰减）
    if article.published_at:
        age_hours = (datetime.now(timezone.utc) - article.published_at).total_seconds() / 3600
        if age_hours <= 24:
            freshness_score = 100.0
        elif age_hours >= 168:  # 7 天
            freshness_score = 0.0
        else:
            freshness_score = 100.0 * (1.0 - (age_hours - 24) / (168 - 24))
    else:
        freshness_score = 50.0  # 无发布时间，给中位分

    # 内容完整度分（有摘要 + 有 AI 处理 = 100）
    completeness = 0
    if article.raw_summary:
        completeness += 50
    if article.ai_processed:
        completeness += 50

    score = (
        source_score * config.source_weight
        + freshness_score * config.freshness_weight
        + completeness * config.completeness_weight
    )
    return round(min(100, max(0, score)), 1)


def score_all_unscored() -> int:
    """对所有未评分新闻计算可信度，返回更新数量。"""
    session = get_session()
    count = 0
    try:
        articles = session.query(NewsArticle).filter(NewsArticle.rule_score.is_(None)).all()
        for article in articles:
            article.rule_score = calculate_credibility_score(article)
            count += 1
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"可信度评分失败: {e}")
    finally:
        session.close()
    return count


# ---- 7 天清理 ----
def cleanup_old_articles() -> int:
    """删除超过保留天数的新闻，返回删除数量。"""
    config = get_config()
    retention_days = config.cleanup.retention_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    session = get_session()
    deleted = 0
    try:
        # 删除 fetched_at（入库时间）早于截止日期的记录
        result = session.query(NewsArticle).filter(NewsArticle.fetched_at < cutoff).delete()
        session.commit()
        deleted = result
        if deleted > 0:
            logger.info(f"7 天清理：已删除 {deleted} 条过期新闻")
    except Exception as e:
        session.rollback()
        logger.error(f"清理失败: {e}")
    finally:
        session.close()
    return deleted
