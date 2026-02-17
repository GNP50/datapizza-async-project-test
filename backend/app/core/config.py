import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env" if Path("../.env").exists() else ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_parse_none_str="None"
    )

    environment: str = Field(default="development")

    database_url: str = Field(default="sqlite+aiosqlite:///./chatbot.db")
    database_pool_size: int = Field(default=20)
    database_echo: bool = Field(default=False)

    redis_url: str = Field(default="redis://localhost:6379/0")
    cache_ttl: int = Field(default=3600)  # Default TTL in seconds for Redis cache entries

    jwt_secret: str = Field(default="change-this-secret-key")
    jwt_algorithm: str = Field(default="HS256")
    access_token_expire_minutes: int = Field(default=30)
    refresh_token_expire_days: int = Field(default=7)

    email_enabled: bool = Field(default=False)
    email_provider: str = Field(default="smtp")
    smtp_host: str | None = None
    smtp_port: int = Field(default=587)
    smtp_username: str | None = None
    smtp_password: str | None = None
    email_from: str = Field(default="noreply@chatbot.com")

    double_check_enabled: bool = Field(default=True)
    verification_token_expire_hours: int = Field(default=24)

    cors_origins: str | list[str] = Field(default="http://localhost:3000")

    storage_provider: str = Field(default="local")
    storage_path: str = Field(default="./data/uploads")
    s3_bucket_name: str | None = None
    aws_region: str = Field(default="us-east-1")

    queue_provider: str = Field(default="redis")
    celery_broker_url: str = Field(default="redis://localhost:6379/0")
    celery_result_backend: str = Field(default="redis://localhost:6379/0")
    sqs_queue_url: str | None = None

    enable_fact_checking: bool = Field(default=True)

    llm_provider: str = Field(default="ollama")
    ollama_base_url: str = Field(default="https://api.ollama.com")
    ollama_api_key: str | None = Field(default=None)
    ollama_model: str = Field(default="gpt-oss:120b-cloud")
    embedding_model: str = Field(default="qwen3-embedding:4b")

    # Embedding provider: auto (follows llm_provider), ollama, openai, openai_like
    embedding_provider: str = Field(default="auto")
    # OpenAI-specific embedding settings (used when embedding_provider=openai)
    openai_embedding_model: str | None = Field(default=None)
    openai_base_url: str | None = Field(default=None)

    # OCR Configuration
    ocr_provider: str = Field(default="pypdf2")  # Options: llm, pypdf2
    ocr_llm_provider: str = Field(default="openai")  # Options: openai, anthropic, google, ollama, openai_like
    ocr_model: str = Field(default="gpt-4o-mini")  # Vision model for OCR

    # OCR API Keys (falls back to main provider keys if not set)
    ocr_openai_api_key: str | None = Field(default=None)
    ocr_anthropic_api_key: str | None = Field(default=None)
    ocr_google_api_key: str | None = Field(default=None)
    ocr_ollama_api_key: str | None = Field(default=None)  # For ollama provider
    ocr_ollama_base_url: str | None = Field(default=None)  # For ollama provider
    ocr_base_url: str | None = Field(default=None)  # For openai_like provider
    ocr_api_key: str | None = Field(default=None)  # For openai_like provider

    # Main LLM API Keys
    openai_api_key: str | None = Field(default=None)
    anthropic_api_key: str | None = Field(default=None)
    google_api_key: str | None = Field(default=None)

    qdrant_url: str = Field(default="http://localhost:6333")
    qdrant_api_key: str | None = Field(default=None)

    # Parallel Processing Configuration
    ocr_parallel: bool = Field(default=False)  # Enable parallel OCR processing per page
    documents_parallel: bool = Field(default=False)  # Enable parallel document processing
    web_verification_parallel: bool = Field(default=False)  # Enable parallel web verification (search + LLM judge)
    ocr_max_concurrency: int = Field(default=3)  # Max concurrent OCR tasks
    documents_max_concurrency: int = Field(default=2)  # Max concurrent document tasks
    web_verification_max_concurrency: int = Field(default=3)  # Max concurrent web verification tasks
    ocr_max_retries: int = Field(default=3)  # Max retries for OCR operations
    documents_max_retries: int = Field(default=3)  # Max retries for document operations
    web_verification_max_retries: int = Field(default=2)  # Max retries for web verification operations

    log_level: str = Field(default="INFO")
    log_file: str | None = Field(default="logs/app.log")
    log_format: str = Field(default="text")

    cloudwatch_logging_enabled: bool = Field(default=False)
    cloudwatch_log_group: str = Field(default="/chatbot/backend")
    cloudwatch_log_stream: str | None = None

    datadog_api_key: str | None = None
    service_name: str = Field(default="chatbot-backend")

    sentry_dsn: str | None = None

    @field_validator("cors_origins")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> list[str]:
        if v is None or v == "":
            return ["http://localhost:3000"]
        if isinstance(v, str):
            if not v.strip():
                return ["http://localhost:3000"]
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return [str(item).strip() for item in v if item]
        if isinstance(v, (tuple, set)):
            return [str(item).strip() for item in v if item]
        return ["http://localhost:3000"]


class ConfigurationManager:
    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or Path("config.yaml")
        self.yaml_config = self._load_yaml_config()
        self.settings = Settings()

    def _load_yaml_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}

        with open(self.config_path, "r") as f:
            return yaml.safe_load(f) or {}

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        value = self.yaml_config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                value = None
                break

        if value is not None:
            return value

        return getattr(self.settings, key.replace(".", "_"), default)


@lru_cache()
def get_config() -> ConfigurationManager:
    return ConfigurationManager()


@lru_cache()
def get_settings() -> Settings:
    return Settings()
