"""应用配置管理。

配置优先级：环境变量 > config.yaml > 代码默认值。
项目根目录会从当前文件向上自动探测，也可以通过 OSINT_CONFIG_DIR 指定。
"""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ServerConfig(ConfigModel):
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


class OllamaConfig(ConfigModel):
    host: str = "http://localhost:11434"
    model: str = "qwen2.5:7b"
    fallback_model: str = "qwen2.5:3b"
    timeout: int = 120


class DeepSeekConfig(ConfigModel):
    api_key: str = ""
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com"


class AIConfig(ConfigModel):
    mode: Literal["mock", "ollama", "deepseek"] = "mock"
    interval_minutes: int = Field(default=5, ge=1)
    batch_size: int = Field(default=20, ge=1, le=200)
    max_input_chars: int = Field(default=12000, ge=1000, le=100000)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    deepseek: DeepSeekConfig = Field(default_factory=DeepSeekConfig)


class CollectorConfig(ConfigModel):
    interval_minutes: int = Field(default=30, ge=1)
    request_timeout: int = Field(default=30, ge=5)
    max_concurrency: int = Field(default=5, ge=1, le=20)
    max_entries_per_source: int = Field(default=100, ge=10, le=500)
    user_agent: str = "OSINT-News-Console/1.1 (RSS Reader)"


class CleanupConfig(ConfigModel):
    retention_days: int = Field(default=7, ge=1)
    schedule_hour: int = Field(default=3, ge=0, le=23)


class RuleEngineConfig(ConfigModel):
    source_weight: float = 0.35
    corroboration_weight: float = 0.30
    freshness_weight: float = 0.15
    completeness_weight: float = 0.20
    official_bonus: float = 8.0

    @model_validator(mode="after")
    def validate_weights(self):
        total = (
            self.source_weight
            + self.corroboration_weight
            + self.freshness_weight
            + self.completeness_weight
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError("rule_engine 的四项 weight 总和必须为 1.0")
        return self


class VerificationConfig(ConfigModel):
    lookback_hours: int = Field(default=72, ge=12, le=336)
    similarity_threshold: float = Field(default=0.58, ge=0.3, le=0.95)
    min_sources: int = Field(default=2, ge=2, le=5)


class SecurityConfig(ConfigModel):
    admin_token: str = ""


class AppConfig(ConfigModel):
    timezone: str = "Asia/Shanghai"
    server: ServerConfig = Field(default_factory=ServerConfig)
    database: dict[str, str] = Field(default_factory=lambda: {"path": "data/news.db"})
    ai: AIConfig = Field(default_factory=AIConfig)
    collector: CollectorConfig = Field(default_factory=CollectorConfig)
    cleanup: CleanupConfig = Field(default_factory=CleanupConfig)
    rule_engine: RuleEngineConfig = Field(default_factory=RuleEngineConfig)
    verification: VerificationConfig = Field(default_factory=VerificationConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)


def get_project_root() -> Path:
    """定位 config.yaml / sources.yaml 所在目录，兼容本地与 Docker。"""
    forced = os.getenv("OSINT_CONFIG_DIR")
    if forced:
        return Path(forced).expanduser().resolve()

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "config.yaml").exists() or (parent / "sources.yaml").exists():
            return parent
    return current.parents[2]


def _load_yaml() -> dict[str, Any]:
    yaml_path = get_project_root() / "config.yaml"
    if not yaml_path.exists():
        return {}
    with yaml_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


_ENV_OVERRIDES: dict[str, tuple[tuple[str, ...], Any]] = {
    "APP_TIMEZONE": (("timezone",), str),
    "SERVER_HOST": (("server", "host"), str),
    "SERVER_PORT": (("server", "port"), int),
    "SERVER_DEBUG": (("server", "debug"), _parse_bool),
    "CORS_ORIGINS": (("server", "cors_origins"), _parse_list),
    "DATABASE_PATH": (("database", "path"), str),
    "AI_MODE": (("ai", "mode"), str),
    "AI_INTERVAL_MINUTES": (("ai", "interval_minutes"), int),
    "AI_BATCH_SIZE": (("ai", "batch_size"), int),
    "AI_MAX_INPUT_CHARS": (("ai", "max_input_chars"), int),
    "OLLAMA_HOST": (("ai", "ollama", "host"), str),
    "OLLAMA_MODEL": (("ai", "ollama", "model"), str),
    "OLLAMA_FALLBACK_MODEL": (("ai", "ollama", "fallback_model"), str),
    "OLLAMA_TIMEOUT": (("ai", "ollama", "timeout"), int),
    "DEEPSEEK_API_KEY": (("ai", "deepseek", "api_key"), str),
    "DEEPSEEK_MODEL": (("ai", "deepseek", "model"), str),
    "DEEPSEEK_BASE_URL": (("ai", "deepseek", "base_url"), str),
    "COLLECTOR_INTERVAL_MINUTES": (("collector", "interval_minutes"), int),
    "COLLECTOR_REQUEST_TIMEOUT": (("collector", "request_timeout"), int),
    "COLLECTOR_MAX_CONCURRENCY": (("collector", "max_concurrency"), int),
    "COLLECTOR_MAX_ENTRIES_PER_SOURCE": (("collector", "max_entries_per_source"), int),
    "CLEANUP_RETENTION_DAYS": (("cleanup", "retention_days"), int),
    "ADMIN_TOKEN": (("security", "admin_token"), str),
}


def _set_nested(data: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    cursor = data
    for key in path[:-1]:
        child = cursor.get(key)
        if not isinstance(child, dict):
            child = {}
            cursor[key] = child
        cursor = child
    cursor[path[-1]] = value


_config: AppConfig | None = None


def get_config() -> AppConfig:
    global _config
    if _config is None:
        data = deepcopy(_load_yaml())
        for env_name, (path, parser) in _ENV_OVERRIDES.items():
            raw = os.getenv(env_name)
            if raw is not None:
                _set_nested(data, path, parser(raw))
        _config = AppConfig.model_validate(data)
    return _config


def reset_config() -> None:
    global _config
    _config = None
