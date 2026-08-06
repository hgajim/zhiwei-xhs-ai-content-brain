"""应用配置。所有配置均从环境变量读取。"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://brand_kb:change_me@localhost:5432/brand_kb",
    )
    embedding_base_url: str = os.getenv(
        "EMBEDDING_BASE_URL", "https://api.openai.com/v1"
    ).rstrip("/")
    embedding_provider: str = os.getenv(
        "EMBEDDING_PROVIDER", "openai-compatible"
    ).strip().lower()
    dashscope_base_url: str = os.getenv("DASHSCOPE_BASE_URL", "").rstrip("/")
    embedding_api_key: str = os.getenv("EMBEDDING_API_KEY", "")
    embedding_model: str = os.getenv(
        "EMBEDDING_MODEL", "text-embedding-3-small"
    )
    embedding_dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
    embedding_timeout_seconds: int = int(
        os.getenv("EMBEDDING_TIMEOUT_SECONDS", "60")
    )
    llm_base_url: str = os.getenv("LLM_BASE_URL", "").rstrip("/")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "qwen-plus")
    llm_timeout_seconds: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
    # 用于加密用户自行填写的模型 API Key。网页部署时必须配置稳定的 Fernet 密钥。
    app_encryption_key: str = os.getenv("APP_ENCRYPTION_KEY", "")
    embedding_query_instruction: str = os.getenv(
        "EMBEDDING_QUERY_INSTRUCTION",
        "Retrieve relevant knowledge passages for the query.",
    )
    allow_deterministic_dev_embedding: bool = _bool(
        "ALLOW_DETERMINISTIC_DEV_EMBEDDING", True
    )
    job_poll_seconds: float = float(os.getenv("JOB_POLL_SECONDS", "2"))
    job_max_attempts: int = int(os.getenv("JOB_MAX_ATTEMPTS", "5"))
    # 图片字节存储在独立目录，PostgreSQL只保存元数据和关联关系。
    asset_storage_dir: str = os.getenv("ASSET_STORAGE_DIR", "data/assets")
    image_max_bytes: int = int(os.getenv("IMAGE_MAX_BYTES", str(15 * 1024 * 1024)))
    image_max_pixels: int = int(os.getenv("IMAGE_MAX_PIXELS", "40000000"))
    image_max_count: int = int(os.getenv("IMAGE_MAX_COUNT", "30"))
    image_download_timeout_seconds: int = int(os.getenv("IMAGE_DOWNLOAD_TIMEOUT_SECONDS", "30"))
    vision_model: str = os.getenv("VISION_MODEL", "qwen3-vl-flash")
    vision_prompt_version: str = os.getenv("VISION_PROMPT_VERSION", "xhs-image-understanding-v1")
    multimodal_embedding_model: str = os.getenv("MULTIMODAL_EMBEDDING_MODEL", "qwen3-vl-embedding")
    multimodal_embedding_dimensions: int = int(os.getenv("MULTIMODAL_EMBEDDING_DIMENSIONS", "1536"))
    auth_session_days: int = int(os.getenv("AUTH_SESSION_DAYS", "30"))


settings = Settings()

if settings.embedding_dimensions != 1536:
    raise RuntimeError("当前数据库迁移固定为 1536 维文本向量，请将 EMBEDDING_DIMENSIONS 设为 1536。")
