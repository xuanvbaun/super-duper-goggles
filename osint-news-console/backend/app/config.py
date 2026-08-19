"""应用配置管理 — Pydantic Settings + YAML 文件加载"""

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic_settings import BaseSettings


class ServerConfig(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    model_config = {"env_prefix": "SERVER_", "extra": "allow"}


class OllamaConfig(BaseSettings):
    host: str = "http://localhost:11434"
    model: str = "qwen2.5:7b"
    fallback_model: str = "qwen3:4b"
    timeout: int = 120
    max_input_tokens: int = 4000

    model_config = {"env_prefix": "OLLAMA_", "extra": "allow"}


class DeepSeekConfig(BaseSettings):
    api_key: str = ""
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com"

    model_config = {"env_prefix": "DEEPSEEK_", "extra": "allow"}


class AIConfig(BaseSettings):
    mode: Literal["mock", "ollama", "deepseek"] = "mock"
    ollama: OllamaConfig = OllamaConfig()
    deepseek: DeepSeekConfig = DeepSeekConfig()

    model_config = {"env_prefix": "AI_", "extra": "allow"}


class CollectorConfig(BaseSettings):
    interval_minutes: int = 30
    request_timeout: int = 30
    user_agent: str = "OSINT-News-Console/1.0 (RSS Reader)"

    model_config = {"env_prefix": "COLLECTOR_", "extra": "allow"}


class CleanupConfig(BaseSettings):
    retention_days: int = 7
    schedule_hour: int = 3

    model_config = {"env_prefix": "CLEANUP_", "extra": "allow"}


class RuleEngineConfig(BaseSettings):
    source_weight: float = 0.6
    freshness_weight: float = 0.2
    completeness_weight: float = 0.2

    model_config = {"env_prefix": "RULE_", "extra": "allow"}


class AppConfig(BaseSettings):
    server: ServerConfig = ServerConfig()
    database: dict = {"path": "data/news.db"}
    ai: AIConfig = AIConfig()
    collector: CollectorConfig = CollectorConfig()
    cleanup: CleanupConfig = CleanupConfig()
    rule_engine: RuleEngineConfig = RuleEngineConfig()


# ---- 加载 YAML 配置 ----
_config: AppConfig | None = None
_BASE_DIR = Path(__file__).resolve().parent.parent.parent  # D:\xd\


def _load_yaml() -> dict:
    """从项目根目录加载 config.yaml，不存在则返回空 dict。"""
    yaml_path = _BASE_DIR / "config.yaml"
    if yaml_path.exists():
        with open(yaml_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _flatten_config(data: dict, prefix: str = "") -> dict:
    """将嵌套字典展平为环境变量风格的扁平字典。"""
    result = {}
    for key, value in data.items():
        full_key = f"{prefix}{key}".upper()
        if isinstance(value, dict):
            result.update(_flatten_config(value, f"{key}_"))
        else:
            result[full_key] = value
    return result


def get_config() -> AppConfig:
    """获取全局配置单例。YAML 文件作为默认值，环境变量优先级更高。"""
    global _config
    if _config is None:
        yaml_data = _load_yaml()
        # 将 YAML 作为默认值注入环境变量（仅当对应环境变量不存在时）
        # Pydantic Settings 自动从环境变量读取，所以 YAML 值通过 os.environ 传入
        flat_data = _flatten_config(yaml_data)
        _injected_keys = []
        for key, value in flat_data.items():
            if key not in os.environ:
                os.environ[key] = str(value)
                _injected_keys.append(key)

        _config = AppConfig()
        # 清理注入的临时变量，避免污染后续进程
        for key in _injected_keys:
            os.environ.pop(key, None)
    return _config


def reset_config() -> None:
    """重置配置缓存（测试用）。"""
    global _config
    _config = None
