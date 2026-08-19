"""AI 处理层 — 摘要/分类/标签提取

架构：
  AIProvider (抽象基类)
     ├── MockProvider   — 开发阶段假数据
     ├── OllamaProvider — 本地 Ollama 模型
     └── DeepSeekProvider — 云端备用（极低频）

约束（硬编码在 Prompt 中）：
  - 仅输出摘要、分类、标签
  - 禁止推测、预测、立场输出、主观评论
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

import httpx

from .config import get_config

logger = logging.getLogger(__name__)

# ---- AI 输出结构 ----
AIResult = dict[str, str | list[str]]
# {"summary": str, "category": str, "tags": list[str]}


# ---- 语言检测 ----
def _is_chinese(text: str) -> bool:
    """检测文本是否主要为中文（基于 CJK 字符比例）。"""
    if not text:
        return False
    cjk_count = sum(1 for c in text if '一' <= c <= '鿿' or '㐀' <= c <= '䶿')
    # 至少 10% 为 CJK 字符视为中文内容
    return len(text) > 0 and (cjk_count / len(text)) > 0.1


# ---- Prompt 模板 ----
SYSTEM_PROMPT = """你是一个新闻摘要助手，**仅用于事实性整理**。你必须严格遵守以下约束：

## 允许的操作
- 对新闻内容做客观摘要（严格不超过 300 字）
- 若 300 字内无法完整表达核心事实，则直接输出原文，不做删减
- 归类到以下类别之一：综合、科技、安全、财经、国际、社会、法律、军事、其他
- 提取 3~5 个关键词标签

## 严禁的操作
- 推测事件原因或未来走向
- 输出任何政治立场、价值判断、主观评论
- 对新闻人物或事件做出评价
- 分析国际局势或地缘政治含义

## 输出格式
严格输出 JSON，不要有任何其他文本：
{"summary": "摘要内容", "category": "类别", "tags": ["标签1", "标签2", "标签3"]}
"""

USER_PROMPT_TEMPLATE = """请处理以下新闻：

标题：{title}
来源：{source}
原始摘要：{raw_summary}

请输出 JSON："""


# ---- 抽象基类 ----
class AIProvider(ABC):
    @abstractmethod
    async def process(self, title: str, source: str, raw_summary: str) -> AIResult:
        """处理单条新闻，返回 {summary, category, tags}"""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """检查提供者是否可用"""
        ...


def _rule_category(title: str, raw_summary: str | None) -> str:
    """基于关键词的简单分类（Mock 模式下使用）。"""
    text = (title + " " + (raw_summary or "")).lower()
    if any(kw in text for kw in ["安全", "漏洞", "攻击", "黑客", "security", "hack", "漏洞"]):
        return "安全"
    if any(kw in text for kw in ["ai", "人工智能", "模型", "gpt", "llm", "代码", "开源", "科技"]):
        return "科技"
    if any(kw in text for kw in ["股", "经济", "金融", "市场", "央行", "财经"]):
        return "财经"
    if any(kw in text for kw in ["国际", "外交", "联合", "世界"]):
        return "国际"
    return "综合"


# ---- Mock 实现 ----
class MockProvider(AIProvider):
    """开发阶段假数据，保证流程可跑通。"""

    async def process(self, title: str, source: str, raw_summary: str) -> AIResult:
        is_cn = _is_chinese(title + (raw_summary or ""))

        # 非中文内容：完整原文，不做截断
        if not is_cn:
            category = _rule_category(title, raw_summary)
            return {
                "summary": raw_summary or title,
                "category": category,
                "tags": ["非中文", category],
            }

        # 中文内容：截取 300 字摘要，不足则保留原文
        category = _rule_category(title, raw_summary)
        full_text = raw_summary or title
        if len(full_text) <= 300:
            summary = full_text
        else:
            summary = full_text[:300]
        return {
            "summary": summary,
            "category": category,
            "tags": [category],
        }

    async def health_check(self) -> bool:
        return True


# ---- Ollama 实现 ----
class OllamaProvider(AIProvider):
    def __init__(self, host: str, model: str, fallback_model: str, timeout: int):
        self.host = host.rstrip("/")
        self.model = model
        self.fallback_model = fallback_model
        self.timeout = timeout

    async def process(self, title: str, source: str, raw_summary: str) -> AIResult:
        user_prompt = USER_PROMPT_TEMPLATE.format(
            title=title,
            source=source,
            raw_summary=raw_summary or "（无原始摘要）",
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 500},
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(f"{self.host}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return self._parse_response(data["message"]["content"])
            except Exception as e:
                logger.warning(f"Ollama 主模型 ({self.model}) 失败: {e}，尝试降级模型")
                # 降级尝试
                if self.fallback_model and self.fallback_model != self.model:
                    try:
                        payload["model"] = self.fallback_model
                        resp = await client.post(f"{self.host}/api/chat", json=payload)
                        resp.raise_for_status()
                        data = resp.json()
                        return self._parse_response(data["message"]["content"])
                    except Exception as e2:
                        logger.error(f"Ollama 降级模型 ({self.fallback_model}) 也失败: {e2}")
                raise

    def _parse_response(self, text: str) -> AIResult:
        """从 LLM 响应中提取 JSON。"""
        text = text.strip()
        # 尝试直接解析
        try:
            result = json.loads(text)
            return {
                "summary": str(result.get("summary", "")),
                "category": str(result.get("category", "未分类")),
                "tags": result.get("tags", []) if isinstance(result.get("tags"), list) else [],
            }
        except json.JSONDecodeError:
            pass
        # 尝试提取 ```json ... ``` 块
        if "```json" in text:
            try:
                block = text.split("```json")[1].split("```")[0].strip()
                result = json.loads(block)
                return {
                    "summary": str(result.get("summary", "")),
                    "category": str(result.get("category", "未分类")),
                    "tags": result.get("tags", []) if isinstance(result.get("tags"), list) else [],
                }
            except Exception:
                pass
        # 降级：返回原文截断作为摘要
        logger.warning(f"无法解析 Ollama 响应 JSON: {text[:200]}")
        return {"summary": text[:200], "category": "未分类", "tags": []}

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.host}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False


# ---- DeepSeek 实现（备用）----
class DeepSeekProvider(AIProvider):
    def __init__(self, api_key: str, model: str, base_url: str):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    async def process(self, title: str, source: str, raw_summary: str) -> AIResult:
        user_prompt = USER_PROMPT_TEMPLATE.format(
            title=title,
            source=source,
            raw_summary=raw_summary or "（无原始摘要）",
        )
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 500,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            # 复用 Ollama 的解析逻辑
            provider = OllamaProvider("", "", "", 30)
            return provider._parse_response(content)

    async def health_check(self) -> bool:
        return bool(self.api_key)


# ---- 工厂函数 ----
_provider: AIProvider | None = None


def get_ai_provider() -> AIProvider:
    """根据配置创建 AI 提供者单例。"""
    global _provider
    if _provider is not None:
        return _provider

    config = get_config()
    mode = config.ai.mode

    if mode == "ollama":
        _provider = OllamaProvider(
            host=config.ai.ollama.host,
            model=config.ai.ollama.model,
            fallback_model=config.ai.ollama.fallback_model,
            timeout=config.ai.ollama.timeout,
        )
    elif mode == "deepseek":
        _provider = DeepSeekProvider(
            api_key=config.ai.deepseek.api_key,
            model=config.ai.deepseek.model,
            base_url=config.ai.deepseek.base_url,
        )
    else:
        logger.info("AI 模式：Mock（开发阶段假数据）")
        _provider = MockProvider()

    return _provider


async def process_unprocessed_articles(batch_size: int = 10) -> int:
    """处理所有未处理的新闻（被调度器和启动事件调用）。"""
    from .database import get_session
    from .models import NewsArticle

    provider = get_ai_provider()
    session = get_session()
    processed = 0

    try:
        articles = (
            session.query(NewsArticle)
            .filter(NewsArticle.ai_processed == False)  # noqa: E712
            .limit(batch_size)
            .all()
        )

        for article in articles:
            try:
                result = await provider.process(
                    title=article.title,
                    source=article.source_name,
                    raw_summary=article.raw_summary or "",
                )
                article.ai_summary = result.get("summary", "")
                article.ai_category = result.get("category", article.source_category)
                article.ai_tags = ",".join(result.get("tags", []))
                article.ai_processed = True
                processed += 1
            except Exception as e:
                logger.error(f"AI 处理失败 [{article.id}]: {e}")

        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"AI 批量处理失败: {e}")
    finally:
        session.close()

    if processed > 0:
        logger.info(f"AI 处理完成：{processed} 条")
    return processed
