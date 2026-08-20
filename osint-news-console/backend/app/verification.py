"""同事件聚类与多来源交叉验证。

这里只标记“有多少独立来源报道同一事件”，不把聚类结果等同于事实真伪结论。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import defaultdict
from datetime import timedelta
from difflib import SequenceMatcher

from .config import get_config
from .database import get_session
from .models import NewsArticle
from .time_utils import utc_now

logger = logging.getLogger(__name__)

_GENERIC_WORDS = {
    "最新",
    "消息",
    "报道",
    "宣布",
    "表示",
    "回应",
    "今日",
    "昨日",
    "中国",
    "新闻",
    "the",
    "and",
    "for",
    "with",
    "from",
    "says",
    "new",
    "latest",
}


def _normalize_title(title: str) -> str:
    text = re.sub(r"\s+", "", (title or "").lower())
    return re.sub(r"[^0-9a-z\u3400-\u9fff]", "", text)


def _title_tokens(title: str) -> set[str]:
    normalized = _normalize_title(title)
    chinese = "".join(re.findall(r"[\u3400-\u9fff]", normalized))
    tokens = {chinese[i : i + 2] for i in range(max(0, len(chinese) - 1))}
    tokens.update(
        word
        for word in re.findall(r"[a-z0-9]{3,}", normalized)
        if word not in _GENERIC_WORDS
    )
    return tokens


def title_similarity(left: str, right: str) -> float:
    """结合字符序列和关键词重合度，避免只依赖完全相同标题。"""
    a = _normalize_title(left)
    b = _normalize_title(right)
    if not a or not b:
        return 0.0
    sequence_score = SequenceMatcher(None, a, b).ratio()
    left_tokens = _title_tokens(left)
    right_tokens = _title_tokens(right)
    union = left_tokens | right_tokens
    token_score = len(left_tokens & right_tokens) / len(union) if union else 0.0
    containment = (
        len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))
        if left_tokens and right_tokens
        else 0.0
    )
    return max(sequence_score, token_score * 0.75 + containment * 0.25)


class _UnionFind:
    def __init__(self, size: int):
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left != root_right:
            self.parent[root_right] = root_left


def cluster_recent_articles() -> dict[str, int]:
    """聚类近期文章并写入来源数量、官方确认状态。"""
    config = get_config().verification
    cutoff = utc_now() - timedelta(hours=config.lookback_hours)
    session = get_session()
    try:
        articles = (
            session.query(NewsArticle)
            .filter(NewsArticle.published_at >= cutoff)
            .order_by(NewsArticle.published_at.asc(), NewsArticle.id.asc())
            .all()
        )
        union_find = _UnionFind(len(articles))

        # 通过标题词元倒排索引生成候选对，避免新闻量增长后进行 O(n²) 全比较。
        token_index: dict[str, set[int]] = defaultdict(set)
        token_cache = [_title_tokens(article.title) for article in articles]
        for right_index, right in enumerate(articles):
            candidates: set[int] = set()
            for token in token_cache[right_index]:
                candidates.update(token_index[token])
            for left_index in candidates:
                left = articles[left_index]
                if left.source_name == right.source_name:
                    continue
                if (
                    title_similarity(left.title, right.title)
                    >= config.similarity_threshold
                ):
                    union_find.union(left_index, right_index)
            for token in token_cache[right_index]:
                token_index[token].add(right_index)

        groups: dict[int, list[NewsArticle]] = defaultdict(list)
        for index, article in enumerate(articles):
            groups[union_find.find(index)].append(article)

        verified_events = 0
        official_events = 0
        for group in groups.values():
            sources = sorted({article.source_name for article in group})
            official = any(article.source_official for article in group)
            event_seed = "|".join(sorted(article.id for article in group))
            event_id = hashlib.sha1(event_seed.encode("utf-8")).hexdigest()[:16]

            if official:
                status = "official_confirmed"
                official_events += 1
            elif len(sources) >= config.min_sources:
                status = "multi_source"
            else:
                status = "single_source"
            if len(sources) >= config.min_sources:
                verified_events += 1

            sources_json = json.dumps(sources, ensure_ascii=False)
            for article in group:
                article.event_id = event_id
                article.corroboration_count = len(sources)
                article.corroborating_sources = sources_json
                article.verification_status = status
                article.official_confirmed = official

        session.commit()
        result = {
            "articles": len(articles),
            "events": len(groups),
            "multi_source_events": verified_events,
            "official_events": official_events,
        }
        logger.info("事件聚类完成：%s", result)
        return result
    except Exception:
        session.rollback()
        logger.exception("事件聚类失败")
        raise
    finally:
        session.close()


def parse_sources(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []
