"""应用配置管理 — Pydantic Settings + YAML 文件加载"""

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field
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
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    deepseek: DeepSeekConfig = Field(default_factory=DeepSeekConfig)

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
    server: ServerConfig = Field(default_factory=ServerConfig)
    database: dict = Field(default_factory=lambda: {"path": "data/news.db"})
    ai: AIConfig = Field(default_factory=AIConfig)
    collector: CollectorConfig = Field(default_factory=CollectorConfig)
    cleanup: CleanupConfig = Field(default_factory=CleanupConfig)
    rule_engine: RuleEngineConfig = Field(default_factory=RuleEngineConfig)


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


def _yaml_defaults(settings_type: type[BaseSettings], values: dict | None) -> dict:
    """返回未被环境变量覆盖的 YAML 设置。"""
    values = values or {}
    env_prefix = str(settings_type.model_config.get("env_prefix", ""))
    env_keys = {key.upper() for key in os.environ}
    return {
        key: value
        for key, value in values.items()
        if f"{env_prefix}{key}".upper() not in env_keys
    }


def _build_config(yaml_data: dict) -> AppConfig:
    """以 YAML 为默认值构建配置，并让环境变量保持最高优先级。"""
    ai_data = yaml_data.get("ai") or {}
    ollama = OllamaConfig(**_yaml_defaults(OllamaConfig, ai_data.get("ollama")))
    deepseek = DeepSeekConfig(**_yaml_defaults(DeepSeekConfig, ai_data.get("deepseek")))
    ai_values = {key: value for key, value in ai_data.items() if key not in {"ollama", "deepseek"}}
    ai = AIConfig(
        ollama=ollama,
        deepseek=deepseek,
        **_yaml_defaults(AIConfig, ai_values),
    )

    database = dict(yaml_data.get("database") or {"path": "data/news.db"})
    if "DATABASE_PATH" in {key.upper() for key in os.environ}:
        database["path"] = os.environ["DATABASE_PATH"]

    return AppConfig(
        server=ServerConfig(**_yaml_defaults(ServerConfig, yaml_data.get("server"))),
        database=database,
        ai=ai,
        collector=CollectorConfig(**_yaml_defaults(CollectorConfig, yaml_data.get("collector"))),
        cleanup=CleanupConfig(**_yaml_defaults(CleanupConfig, yaml_data.get("cleanup"))),
        rule_engine=RuleEngineConfig(**_yaml_defaults(RuleEngineConfig, yaml_data.get("rule_engine"))),
    )


def get_config() -> AppConfig:
    """获取全局配置单例。YAML 文件作为默认值，环境变量优先级更高。"""
    global _config
    if _config is None:
        _config = _build_config(_load_yaml())
    return _config


def reset_config() -> None:
    """重置配置缓存（测试用）。"""
    global _config
    _config = None
