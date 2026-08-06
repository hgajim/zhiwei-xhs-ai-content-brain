"""品牌级大模型配置；负责 API Key 加密、读取和脱敏。"""

from __future__ import annotations

from typing import Any
from pathlib import Path
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from psycopg import Connection

from app.config import settings
from app.services.knowledge import get_brand


def _fernet() -> Fernet:
    encryption_key = settings.app_encryption_key
    if not encryption_key and settings.app_env == "development":
        # 本地测试自动生成机器私有密钥；文件已加入 .gitignore。
        key_path = Path(__file__).resolve().parents[2] / ".local_encryption_key"
        if not key_path.exists():
            key_path.write_bytes(Fernet.generate_key())
        encryption_key = key_path.read_text(encoding="utf-8").strip()
    if not encryption_key:
        raise ValueError("生产环境未配置 APP_ENCRYPTION_KEY，不能安全保存用户 API Key。")
    try:
        return Fernet(encryption_key.encode("utf-8"))
    except ValueError as exc:
        raise ValueError("APP_ENCRYPTION_KEY 格式无效，必须是 Fernet 密钥。") from exc


def encrypt_api_key(api_key: str) -> str:
    return _fernet().encrypt(api_key.encode("utf-8")).decode("utf-8")


def decrypt_api_key(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("模型 API Key 无法解密，请重新保存配置。") from exc


def upsert_ai_setting(conn: Connection, brand_code: str, data: dict[str, Any]) -> dict[str, Any]:
    brand = get_brand(conn, brand_code)
    parsed_url = urlparse(data["base_url"])
    is_local = parsed_url.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed_url.scheme not in ({"http", "https"} if is_local else {"https"}) or not parsed_url.hostname:
        raise ValueError("模型地址必须是 HTTPS；本地 localhost 测试可使用 HTTP。")
    if parsed_url.username or parsed_url.password:
        raise ValueError("模型地址不能包含用户名或密码。")
    existing = conn.execute(
        "SELECT api_key_encrypted FROM brand_ai_settings WHERE brand_id=%s AND purpose=%s",
        (brand["id"], data["purpose"]),
    ).fetchone()
    api_key = data.get("api_key")
    if api_key:
        encrypted = encrypt_api_key(api_key)
    elif existing:
        encrypted = existing["api_key_encrypted"]
    else:
        raise ValueError("首次配置必须填写 API Key。")
    row = conn.execute(
        """INSERT INTO brand_ai_settings(
               brand_id, purpose, provider, base_url, model_name,
               api_key_encrypted, enabled, extra_options
           ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
           ON CONFLICT (brand_id, purpose) DO UPDATE SET
               provider=EXCLUDED.provider, base_url=EXCLUDED.base_url,
               model_name=EXCLUDED.model_name, api_key_encrypted=EXCLUDED.api_key_encrypted,
               enabled=EXCLUDED.enabled, extra_options=EXCLUDED.extra_options, updated_at=now()
           RETURNING id, purpose, provider, base_url, model_name, enabled, extra_options,
                     created_at, updated_at""",
        (brand["id"], data["purpose"], data["provider"], data["base_url"].rstrip("/"),
         data["model_name"], encrypted, data["enabled"], __import__("json").dumps(data["extra_options"])),
    ).fetchone()
    return {**row, "api_key_configured": True, "api_key_masked": "••••••••"}


def get_ai_setting(conn: Connection, brand_code: str, purpose: str, *, include_secret: bool = False) -> dict[str, Any] | None:
    brand = get_brand(conn, brand_code)
    row = conn.execute(
        "SELECT * FROM brand_ai_settings WHERE brand_id=%s AND purpose=%s AND enabled=true",
        (brand["id"], purpose),
    ).fetchone()
    if not row:
        return None
    public = {k: v for k, v in row.items() if k != "api_key_encrypted"}
    public.update({"api_key_configured": True, "api_key_masked": "••••••••"})
    if include_secret:
        public["api_key"] = decrypt_api_key(row["api_key_encrypted"])
    return public


def delete_ai_setting(conn: Connection, brand_code: str, purpose: str) -> bool:
    """删除指定用途的模型配置及加密API Key。该操作不可恢复。"""
    brand = get_brand(conn, brand_code)
    deleted = conn.execute(
        "DELETE FROM brand_ai_settings WHERE brand_id=%s AND purpose=%s RETURNING id",
        (brand["id"], purpose),
    ).fetchone()
    return deleted is not None
