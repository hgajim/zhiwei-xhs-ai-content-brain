"""来源、知识版本、切片和审批服务。"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from psycopg import Connection

from app.config import settings
from app.services.chunking import normalize_text, segment_for_search, semantic_chunks


def sha256_text(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def get_brand(conn: Connection, brand_code: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id, code, name FROM brands WHERE code = %s", (brand_code,)
    ).fetchone()
    if not row:
        raise ValueError(f"品牌不存在：{brand_code}")
    return row


def create_brand(conn: Connection, code: str, name: str, timezone: str) -> dict[str, Any]:
    return conn.execute(
        """
        INSERT INTO brands(code, name, timezone)
        VALUES (%s, %s, %s)
        ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, updated_at = now()
        RETURNING id, code, name, timezone
        """,
        (code, name, timezone),
    ).fetchone()


def create_source(conn: Connection, data: dict[str, Any]) -> dict[str, Any]:
    brand = get_brand(conn, data["brand_code"])
    source = conn.execute(
        """
        INSERT INTO kb_sources(
            brand_id, source_type, external_id, title, original_uri,
            owner, authority_level, metadata
        ) VALUES (%s, %s::source_type, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (brand_id, source_type, external_id)
        DO UPDATE SET title = EXCLUDED.title, original_uri = EXCLUDED.original_uri,
                      owner = EXCLUDED.owner, metadata = EXCLUDED.metadata
        RETURNING id, brand_id, title, source_type, external_id
        """,
        (
            brand["id"], data["source_type"], data.get("external_id"),
            data["title"], data.get("original_uri"), data.get("owner"),
            data["authority_level"], json.dumps(data.get("metadata", {}), ensure_ascii=False),
        ),
    ).fetchone()

    text = data.get("text") or ""
    content_hash = sha256_text(text or data.get("storage_uri") or data["title"])
    existing = conn.execute(
        """
        SELECT id, version_number, content_hash
        FROM kb_source_versions
        WHERE source_id = %s AND content_hash = %s
        """,
        (source["id"], content_hash),
    ).fetchone()
    if existing:
        return {**source, "source_version": existing, "deduplicated": True}

    next_version = conn.execute(
        "SELECT coalesce(max(version_number), 0) + 1 AS n FROM kb_source_versions WHERE source_id = %s",
        (source["id"],),
    ).fetchone()["n"]
    version = conn.execute(
        """
        INSERT INTO kb_source_versions(
            source_id, version_number, content_hash, raw_text,
            storage_uri, mime_type, metadata
        ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
        RETURNING id, version_number, content_hash
        """,
        (
            source["id"], next_version, content_hash, text or None,
            data.get("storage_uri"), data.get("mime_type"),
            json.dumps(data.get("metadata", {}), ensure_ascii=False),
        ),
    ).fetchone()
    return {**source, "source_version": version, "deduplicated": False}


def create_knowledge(conn: Connection, data: dict[str, Any]) -> dict[str, Any]:
    brand = get_brand(conn, data["brand_code"])
    item = conn.execute(
        """
        INSERT INTO kb_items(brand_id, knowledge_type, canonical_key, title)
        VALUES (%s, %s::knowledge_type, %s, %s)
        ON CONFLICT (brand_id, canonical_key)
        DO UPDATE SET title = EXCLUDED.title
        RETURNING id, brand_id, knowledge_type, canonical_key, title
        """,
        (brand["id"], data["knowledge_type"], data["canonical_key"], data["title"]),
    ).fetchone()
    next_version = conn.execute(
        "SELECT coalesce(max(version_number), 0) + 1 AS n FROM kb_item_versions WHERE item_id = %s",
        (item["id"],),
    ).fetchone()["n"]
    previous = conn.execute(
        """
        SELECT id FROM kb_item_versions
        WHERE item_id = %s AND status IN ('active', 'reviewed')
        ORDER BY version_number DESC LIMIT 1
        """,
        (item["id"],),
    ).fetchone()
    version = conn.execute(
        """
        INSERT INTO kb_item_versions(
            item_id, source_version_id, version_number, status,
            summary, content, authority_level, confidence,
            scope, attributes, supersedes_version_id
        ) VALUES (%s, %s, %s, 'candidate', %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
        RETURNING id, item_id, version_number, status
        """,
        (
            item["id"], data.get("source_version_id"), next_version,
            data["summary"], data["content"], data["authority_level"],
            data.get("confidence"), json.dumps(data.get("scope", {}), ensure_ascii=False),
            json.dumps(data.get("attributes", {}), ensure_ascii=False),
            previous["id"] if previous else None,
        ),
    ).fetchone()

    explicit_chunks = data.get("chunks", [])
    if explicit_chunks:
        chunks = explicit_chunks
    else:
        chunks = [
            {"chunk_type": "rule", "text": text, "search_terms": "", "metadata": {}}
            for text in semantic_chunks(data["content"])
        ]

    chunk_ids: list[UUID] = []
    for ordinal, chunk in enumerate(chunks):
        text = normalize_text(chunk["text"])
        row = conn.execute(
            """
            INSERT INTO kb_chunks(
                brand_id, item_version_id, chunk_type, ordinal,
                text, search_terms, content_hash, metadata, active
            ) VALUES (%s, %s, %s::chunk_type, %s, %s, %s, %s, %s::jsonb, false)
            RETURNING id
            """,
            (
                brand["id"], version["id"], chunk["chunk_type"], ordinal,
                text, chunk.get("search_terms") or segment_for_search(text), sha256_text(text),
                json.dumps(chunk.get("metadata", {}), ensure_ascii=False),
            ),
        ).fetchone()
        chunk_ids.append(row["id"])

    return {**item, "version": version, "chunk_ids": chunk_ids}


def approve_knowledge(
    conn: Connection, version_id: UUID, data: dict[str, Any]
) -> dict[str, Any]:
    version = conn.execute(
        """
        UPDATE kb_item_versions
        SET status = 'reviewed', authority_level = %s, confidence = %s,
            scope = coalesce(%s::jsonb, scope),
            attributes = coalesce(%s::jsonb, attributes),
            approved_by = %s, approved_at = now()
        WHERE id = %s AND status IN ('candidate', 'contested')
        RETURNING id, item_id, status
        """,
        (
            data["authority_level"], data["confidence"],
            json.dumps(data["scope"], ensure_ascii=False) if data.get("scope") is not None else None,
            json.dumps(data["attributes"], ensure_ascii=False) if data.get("attributes") is not None else None,
            data["approved_by"], version_id,
        ),
    ).fetchone()
    if not version:
        raise ValueError("知识版本不存在，或当前状态不允许审批。")

    model_key = (
        f"{settings.embedding_provider}:{settings.embedding_model}:"
        f"{settings.embedding_dimensions}:document-v1"
    )
    conn.execute(
        "UPDATE embedding_models SET active = false WHERE modality = 'text' AND model_key <> %s",
        (model_key,),
    )
    model = conn.execute(
        """
        INSERT INTO embedding_models(
            model_key, provider, model_name, modality, dimensions, normalized, active
        ) VALUES (%s, %s, %s, 'text', %s, true, true)
        ON CONFLICT (model_key) DO UPDATE SET active = true
        RETURNING id
        """,
        (
            model_key,
            settings.embedding_provider, settings.embedding_model, settings.embedding_dimensions,
        ),
    ).fetchone()
    chunks = conn.execute(
        "SELECT id, brand_id FROM kb_chunks WHERE item_version_id = %s ORDER BY ordinal",
        (version_id,),
    ).fetchall()
    for chunk in chunks:
        conn.execute(
            """
            INSERT INTO kb_jobs(brand_id, job_type, entity_type, entity_id, payload, max_attempts)
            VALUES (%s, 'embed_chunk', 'kb_chunk', %s, %s::jsonb, %s)
            """,
            (
                chunk["brand_id"], chunk["id"],
                json.dumps({"model_id": str(model["id"])}), settings.job_max_attempts,
            ),
        )
    return {"version_id": version_id, "status": "reviewed", "queued_chunks": len(chunks)}
