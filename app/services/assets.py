"""图片下载、校验、去重、持久化与文章版本关联。"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import socket
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

from PIL import Image, UnidentifiedImageError
from psycopg import Connection

from app.config import settings


ALLOWED_MIME_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def validate_public_image_url(url: str) -> str:
    """拒绝本机、内网和非 HTTP(S) 地址，避免图片导入成为 SSRF 入口。"""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("图片地址必须是有效的 HTTP 或 HTTPS 地址。")
    if parsed.username or parsed.password:
        raise ValueError("图片地址不能包含账号信息。")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
    except socket.gaierror as exc:
        raise ValueError("图片域名无法解析。") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("图片地址不能指向本机或内网。")
    return parsed.geturl()


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        validate_public_image_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download_image(url: str) -> tuple[bytes, str, int, int]:
    safe_url = validate_public_image_url(url)
    request = Request(
        safe_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "image/avif,image/webp,image/png,image/jpeg,*/*;q=0.5",
            "Referer": "https://www.xiaohongshu.com/",
        },
    )
    try:
        with build_opener(_SafeRedirectHandler()).open(
            request, timeout=settings.image_download_timeout_seconds
        ) as response:
            content_type = response.headers.get_content_type().lower()
            if content_type not in ALLOWED_MIME_TYPES:
                raise ValueError(f"不支持的图片格式：{content_type}")
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > settings.image_max_bytes:
                raise ValueError("图片超过允许的大小。")
            payload = response.read(settings.image_max_bytes + 1)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ValueError(f"图片下载失败：{exc}") from exc
    if len(payload) > settings.image_max_bytes:
        raise ValueError("图片超过允许的大小。")
    try:
        with Image.open(BytesIO(payload)) as image:
            image.verify()
        with Image.open(BytesIO(payload)) as image:
            width, height = image.size
            detected_mime = Image.MIME.get(image.format or "", content_type)
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("下载内容不是有效图片。") from exc
    if detected_mime not in ALLOWED_MIME_TYPES:
        raise ValueError(f"不支持的图片格式：{detected_mime}")
    if width * height > settings.image_max_pixels:
        raise ValueError("图片像素尺寸超过允许范围。")
    return payload, detected_mime, width, height


def _store_bytes(payload: bytes, brand_code: str, mime_type: str) -> tuple[str, str]:
    content_hash = hashlib.sha256(payload).hexdigest()
    extension = ALLOWED_MIME_TYPES[mime_type]
    relative_path = Path(brand_code) / content_hash[:2] / f"{content_hash}{extension}"
    root = Path(settings.asset_storage_dir).resolve()
    target = (root / relative_path).resolve()
    if root not in target.parents:
        raise ValueError("图片存储路径无效。")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(payload)
        os.replace(temporary, target)
    return relative_path.as_posix(), content_hash


def ingest_article_images(
    conn: Connection, article_version_id: UUID, urls: list[str] | None = None
) -> dict[str, Any]:
    """摄入文章图片；逐张隔离错误，重复文件只保存一份。"""
    version = conn.execute(
        """
        SELECT v.id, v.source_version_id, a.brand_id, a.metadata, b.code AS brand_code
        FROM xhs_article_versions v
        JOIN xhs_articles a ON a.id = v.article_id
        JOIN brands b ON b.id = a.brand_id
        WHERE v.id = %s
        """,
        (article_version_id,),
    ).fetchone()
    if not version:
        raise ValueError("文章版本不存在。")
    image_urls = urls if urls is not None else list((version["metadata"] or {}).get("image_urls", []))
    image_urls = list(dict.fromkeys(str(url).strip() for url in image_urls if str(url).strip()))
    if len(image_urls) > settings.image_max_count:
        raise ValueError(f"单篇文章最多摄入 {settings.image_max_count} 张图片。")

    stored = failed = 0
    assets: list[dict[str, Any]] = []
    for ordinal, source_url in enumerate(image_urls):
        try:
            payload, mime_type, width, height = _download_image(source_url)
            storage_uri, content_hash = _store_bytes(
                payload, version["brand_code"], mime_type
            )
            asset = conn.execute(
                """
                INSERT INTO kb_assets(
                    brand_id, source_version_id, asset_type, storage_uri,
                    content_hash, mime_type, width, height, metadata
                ) VALUES (%s,%s,'image',%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (brand_id, content_hash) DO UPDATE
                SET storage_uri=excluded.storage_uri,
                    mime_type=excluded.mime_type,
                    width=excluded.width, height=excluded.height
                RETURNING id, storage_uri, mime_type, width, height, content_hash
                """,
                (
                    version["brand_id"], version["source_version_id"], storage_uri,
                    content_hash, mime_type, width, height,
                    '{"ingestion_source":"xiaohongshu_article"}',
                ),
            ).fetchone()
            link = conn.execute(
                """
                INSERT INTO xhs_article_assets(
                    article_version_id, asset_id, ordinal, source_url, status
                ) VALUES (%s,%s,%s,%s,'stored')
                ON CONFLICT (article_version_id, ordinal) DO UPDATE
                SET asset_id=excluded.asset_id, source_url=excluded.source_url,
                    status='stored', error_message=NULL, updated_at=now()
                RETURNING id
                """,
                (article_version_id, asset["id"], ordinal, source_url),
            ).fetchone()
            stored += 1
            assets.append({**dict(asset), "link_id": link["id"], "ordinal": ordinal})
            conn.execute(
                """INSERT INTO kb_jobs(brand_id,job_type,entity_type,entity_id,payload,max_attempts)
                   SELECT %s,'analyze_image','asset',%s,%s::jsonb,3
                   WHERE NOT EXISTS (
                     SELECT 1 FROM kb_jobs WHERE job_type='analyze_image' AND entity_id=%s
                       AND payload->>'article_version_id'=%s AND status IN ('pending','running','succeeded')
                   )""",
                (version["brand_id"], asset["id"],
                 __import__("json").dumps({"article_version_id": str(article_version_id), "ordinal": ordinal}),
                 asset["id"], str(article_version_id)),
            )
        except Exception as exc:
            failed += 1
            conn.execute(
                """
                INSERT INTO xhs_article_assets(
                    article_version_id, ordinal, source_url, status, error_message
                ) VALUES (%s,%s,%s,'failed',%s)
                ON CONFLICT (article_version_id, ordinal) DO UPDATE
                SET asset_id=NULL, source_url=excluded.source_url,
                    status='failed', error_message=excluded.error_message, updated_at=now()
                """,
                (article_version_id, ordinal, source_url, str(exc)[:1000]),
            )
    return {"total": len(image_urls), "stored": stored, "failed": failed, "assets": assets}


def list_article_images(conn: Connection, article_version_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT link.id, link.ordinal, link.source_url, link.status, link.error_message,
               link.created_at, asset.id AS asset_id, asset.mime_type,
               asset.width, asset.height, asset.content_hash,
               analysis.id AS analysis_id, analysis.status AS analysis_status,
               analysis.asset_role, analysis.visual_type, analysis.summary AS analysis_summary,
               analysis.ocr_text, analysis.product_exposure, analysis.aesthetic,
               analysis.content_functions, analysis.brand_fit_score, analysis.cover_click_score,
               analysis.selling_power_score, analysis.compliance_risks,
               analysis.reusable_visual_rules, analysis.confidence AS analysis_confidence,
               analysis.error_message AS analysis_error,
               coalesce(vectors.vector_count,0)::int AS multimodal_vector_count
        FROM xhs_article_assets link
        LEFT JOIN kb_assets asset ON asset.id = link.asset_id
        LEFT JOIN xhs_image_analyses analysis ON analysis.asset_id=asset.id
          AND analysis.article_version_id=link.article_version_id
        LEFT JOIN LATERAL (
          SELECT count(*) AS vector_count FROM kb_multimodal_embeddings vector
          WHERE vector.asset_id=asset.id AND vector.article_version_id=link.article_version_id AND vector.active=true
        ) vectors ON true
        WHERE link.article_version_id = %s
        ORDER BY link.ordinal
        """,
        (article_version_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def queue_article_image_analysis(conn: Connection, article_version_id: UUID, force: bool = False) -> dict[str, Any]:
    """为已保存图片创建理解任务；默认跳过已完成结果。"""
    rows = conn.execute(
        """SELECT link.asset_id,link.ordinal,article.brand_id
           FROM xhs_article_assets link JOIN xhs_article_versions version ON version.id=link.article_version_id
           JOIN xhs_articles article ON article.id=version.article_id
           WHERE link.article_version_id=%s AND link.status='stored' AND link.asset_id IS NOT NULL""",
        (article_version_id,),
    ).fetchall()
    queued = skipped = 0
    for row in rows:
        if force:
            # 同一张去重图片可能被多篇文章复用，强制重学不能误删其他文章的任务。
            conn.execute(
                """DELETE FROM kb_jobs WHERE entity_id=%s
                   AND job_type IN ('analyze_image','embed_image') AND status<>'running'
                   AND payload->>'article_version_id'=%s""",
                (row["asset_id"], str(article_version_id)),
            )
            conn.execute("DELETE FROM xhs_image_analyses WHERE asset_id=%s AND article_version_id=%s", (row["asset_id"],article_version_id))
        exists = conn.execute(
            """SELECT 1 FROM kb_jobs WHERE entity_id=%s AND job_type='analyze_image'
               AND payload->>'article_version_id'=%s AND status IN ('pending','running','succeeded')""",
            (row["asset_id"],str(article_version_id)),
        ).fetchone()
        if exists:
            skipped += 1; continue
        conn.execute(
            """INSERT INTO kb_jobs(brand_id,job_type,entity_type,entity_id,payload,max_attempts)
               VALUES (%s,'analyze_image','asset',%s,%s::jsonb,3)""",
            (row["brand_id"],row["asset_id"],__import__("json").dumps({"article_version_id":str(article_version_id),"ordinal":row["ordinal"]})),
        )
        queued += 1
    return {"article_version_id":article_version_id,"total_images":len(rows),"queued":queued,"skipped":skipped}


def resolve_asset_path(conn: Connection, asset_id: UUID) -> tuple[Path, str]:
    asset = conn.execute(
        "SELECT storage_uri, mime_type FROM kb_assets WHERE id=%s", (asset_id,)
    ).fetchone()
    if not asset:
        raise ValueError("图片资产不存在。")
    root = Path(settings.asset_storage_dir).resolve()
    path = (root / asset["storage_uri"]).resolve()
    if root not in path.parents or not path.is_file():
        raise ValueError("图片文件不存在。")
    return path, asset["mime_type"] or "application/octet-stream"
