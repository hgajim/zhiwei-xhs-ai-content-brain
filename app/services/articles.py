"""小红书文章摄入、版本、审核和知识沉淀服务。"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from psycopg import Connection

from app.services.article_chunking import build_article_chunks, normalize_article
from app.services.assets import list_article_images
from app.services.knowledge import (
    approve_knowledge,
    create_knowledge,
    create_source,
    get_brand,
    sha256_text,
)


def _source_type(article_type: str) -> str:
    if article_type == "competitor_content":
        return "competitor_content"
    if article_type in {"approved_creator_content", "published_creator_content"}:
        return "reviewed_creator_content"
    return "xiaohongshu_article"


def _source_text(title: str, body: str, hashtags: list[str]) -> str:
    parts = [part for part in [title, body] if part]
    if hashtags:
        parts.append(" ".join(f"#{tag}" for tag in hashtags))
    return "\n\n".join(parts)


def _find_article(conn: Connection, brand_id: UUID, data: dict[str, Any]) -> dict | None:
    if data.get("platform_note_id"):
        row = conn.execute(
            "SELECT * FROM xhs_articles WHERE brand_id = %s AND platform_note_id = %s",
            (brand_id, data["platform_note_id"]),
        ).fetchone()
        if row:
            return row
    if data.get("external_id"):
        return conn.execute(
            "SELECT * FROM xhs_articles WHERE brand_id = %s AND external_id = %s",
            (brand_id, data["external_id"]),
        ).fetchone()
    return None


def create_article(conn: Connection, data: dict[str, Any]) -> dict[str, Any]:
    """保存一篇文章或新增一个稿件版本，并生成结构片段。"""
    brand = get_brand(conn, data["brand_code"])
    title, body, hashtags = normalize_article(
        data.get("title", ""), data.get("body", ""), data.get("hashtags", [])
    )
    if not title and not body:
        raise ValueError("文章标题和正文不能同时为空。")

    combined_text = _source_text(title, body, hashtags)
    source_external_id = data.get("external_id") or data.get("platform_note_id")
    source = create_source(
        conn,
        {
            "brand_code": data["brand_code"],
            "source_type": _source_type(data["article_type"]),
            "external_id": source_external_id,
            "title": title or f"小红书文章-{source_external_id or '未命名'}",
            "text": combined_text,
            "original_uri": data.get("source_url"),
            "owner": data.get("creator_name"),
            "authority_level": data.get("authority_level", 5),
            "metadata": {
                **data.get("metadata", {}),
                "article_type": data["article_type"],
                "product_code": data.get("product_code"),
                "campaign_code": data.get("campaign_code"),
                "creator_type": data.get("creator_type"),
            },
        },
    )

    article = _find_article(conn, brand["id"], data)
    if article:
        article = conn.execute(
            """
            UPDATE xhs_articles
            SET creator_id = coalesce(%s, creator_id),
                creator_name = coalesce(%s, creator_name),
                creator_type = coalesce(%s, creator_type),
                product_code = coalesce(%s, product_code),
                campaign_code = coalesce(%s, campaign_code),
                content_type = coalesce(%s, content_type),
                source_url = coalesce(%s, source_url),
                published_at = coalesce(%s, published_at),
                metadata = metadata || %s::jsonb,
                updated_at = now()
            WHERE id = %s
            RETURNING *
            """,
            (
                data.get("creator_id"), data.get("creator_name"),
                data.get("creator_type"), data.get("product_code"),
                data.get("campaign_code"), data.get("content_type"),
                data.get("source_url"), data.get("published_at"),
                json.dumps(data.get("metadata", {}), ensure_ascii=False), article["id"],
            ),
        ).fetchone()
    else:
        article = conn.execute(
            """
            INSERT INTO xhs_articles(
                brand_id, source_id, article_type, platform_note_id, external_id,
                creator_id, creator_name, creator_type, product_code, campaign_code,
                content_type, source_url, published_at, metadata
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
            ) RETURNING *
            """,
            (
                brand["id"], source["id"], data["article_type"],
                data.get("platform_note_id"), data.get("external_id"),
                data.get("creator_id"), data.get("creator_name"), data.get("creator_type"),
                data.get("product_code"), data.get("campaign_code"), data.get("content_type"),
                data.get("source_url"), data.get("published_at"),
                json.dumps(data.get("metadata", {}), ensure_ascii=False),
            ),
        ).fetchone()

    metrics=data.get("metadata",{})
    if any(metrics.get(key) is not None for key in ("like_count","collect_count","comment_count","share_count")):
        conn.execute("""INSERT INTO xhs_article_interaction_snapshots(article_id,like_count,collect_count,comment_count,share_count)
          VALUES(%s,%s,%s,%s,%s)""",(article["id"],metrics.get("like_count"),metrics.get("collect_count"),metrics.get("comment_count"),metrics.get("share_count")))
    content_hash = sha256_text(combined_text)
    existing = conn.execute(
        """
        SELECT id, version_number, status, content_hash
        FROM xhs_article_versions
        WHERE article_id = %s AND content_hash = %s
        """,
        (article["id"], content_hash),
    ).fetchone()
    if existing:
        return {
            "article_id": article["id"],
            "article_version_id": existing["id"],
            "version_number": existing["version_number"],
            "status": existing["status"],
            "deduplicated": True,
            "chunk_count": conn.execute(
                "SELECT count(*) AS n FROM xhs_article_chunks WHERE article_version_id = %s",
                (existing["id"],),
            ).fetchone()["n"],
        }

    next_version = conn.execute(
        "SELECT coalesce(max(version_number), 0) + 1 AS n FROM xhs_article_versions WHERE article_id = %s",
        (article["id"],),
    ).fetchone()["n"]
    version = conn.execute(
        """
        INSERT INTO xhs_article_versions(
            article_id, source_version_id, version_number, version_type,
            title, body, hashtags, mentioned_products, normalized_text,
            content_hash, status, metadata
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'parsed', %s::jsonb)
        RETURNING *
        """,
        (
            article["id"], source["source_version"]["id"], next_version,
            data["version_type"], title, body, hashtags,
            data.get("mentioned_products", []), combined_text, content_hash,
            json.dumps(data.get("version_metadata", {}), ensure_ascii=False),
        ),
    ).fetchone()

    context = {
        "brand_name": brand["name"],
        "article_type": data["article_type"],
        "product_code": data.get("product_code"),
        "creator_type": data.get("creator_type"),
        "content_type": data.get("content_type"),
        "version_type": data["version_type"],
    }
    chunks = build_article_chunks(title, body, hashtags, context)
    for ordinal, chunk in enumerate(chunks):
        conn.execute(
            """
            INSERT INTO xhs_article_chunks(
                brand_id, article_version_id, chunk_type, ordinal,
                original_text, embedding_text, search_terms, content_hash, metadata
            ) VALUES (%s, %s, %s::chunk_type, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                brand["id"], version["id"], chunk["chunk_type"], ordinal,
                chunk["original_text"], chunk["embedding_text"], chunk["search_terms"],
                sha256_text(chunk["embedding_text"]),
                json.dumps(chunk.get("metadata", {}), ensure_ascii=False),
            ),
        )
    return {
        "article_id": article["id"],
        "article_version_id": version["id"],
        "version_number": next_version,
        "status": version["status"],
        "deduplicated": False,
        "chunk_count": len(chunks),
    }


def list_articles(conn: Connection, brand_code: str, limit: int = 100) -> list[dict[str, Any]]:
    """返回文章库需要的真实文章、最新版本以及最近一次吸收状态。"""
    brand = get_brand(conn, brand_code)
    rows = conn.execute(
        """
        SELECT
            a.id, a.article_type, a.creator_name, a.product_code, a.source_url,
            a.created_at, a.updated_at,
            v.id AS latest_version_id, v.version_type, v.title, v.body,
            v.knowledge_version_id,
            v.status AS version_status, v.created_at AS version_created_at,
            learning.id AS learning_session_id,
            learning.learning_mode, learning.learning_status,
            learning.analysis_summary, learning.insight_count,
            learning.knowledge_count, learning.completed_at, learning.confirmed_at,
            images.image_count, images.failed_image_count, images.first_asset_id,
            images.images_understood, images.multimodal_vector_count,
            metrics.like_count, metrics.collect_count, metrics.comment_count, metrics.share_count,
            content_label.primary_type AS content_primary_type,
            content_label.secondary_types AS content_secondary_types,
            content_label.confidence AS content_type_confidence,
            a.published_at
        FROM xhs_articles a
        JOIN LATERAL (
            SELECT av.* FROM xhs_article_versions av
            WHERE av.article_id = a.id
            ORDER BY av.version_number DESC LIMIT 1
        ) v ON true
        LEFT JOIN LATERAL (
            SELECT ls.id, ls.learning_mode, ls.status AS learning_status,
                   ls.analysis_summary, ls.completed_at, ls.confirmed_at,
                   count(li.id)::int AS insight_count,
                   count(li.knowledge_version_id)::int AS knowledge_count
            FROM xhs_learning_sessions ls
            LEFT JOIN xhs_learning_insights li ON li.session_id = ls.id
            WHERE EXISTS (
                SELECT 1 FROM xhs_article_versions linked_version
                WHERE linked_version.article_id = a.id
                  AND linked_version.id IN (
                      ls.original_article_version_id, ls.revised_article_version_id
                  )
            )
            GROUP BY ls.id
            ORDER BY ls.created_at DESC LIMIT 1
        ) learning ON true
        LEFT JOIN LATERAL (
            SELECT count(*) FILTER (WHERE link.status='stored')::int AS image_count,
                   count(*) FILTER (WHERE link.status='failed')::int AS failed_image_count,
                   count(DISTINCT analysis.id) FILTER (WHERE analysis.status='succeeded')::int AS images_understood,
                   count(DISTINCT vector.id) FILTER (WHERE vector.active=true)::int AS multimodal_vector_count,
                   (array_agg(link.asset_id ORDER BY link.ordinal)
                       FILTER (WHERE link.status='stored'))[1] AS first_asset_id
            FROM xhs_article_assets link
            JOIN xhs_article_versions image_version
              ON image_version.id = link.article_version_id
            LEFT JOIN xhs_image_analyses analysis ON analysis.asset_id=link.asset_id
              AND analysis.article_version_id=link.article_version_id
            LEFT JOIN kb_multimodal_embeddings vector ON vector.asset_id=link.asset_id
              AND vector.article_version_id=link.article_version_id
            WHERE image_version.article_id = a.id
        ) images ON true
        LEFT JOIN LATERAL (
          SELECT like_count,collect_count,comment_count,share_count FROM xhs_article_interaction_snapshots
          WHERE article_id=a.id ORDER BY captured_at DESC LIMIT 1
        ) metrics ON true
        LEFT JOIN LATERAL (
          SELECT label.primary_type, label.secondary_types, label.confidence
          FROM xhs_content_type_labels label
          JOIN xhs_article_versions label_version ON label_version.id=label.article_version_id
          WHERE label_version.article_id=a.id
          ORDER BY label.created_at DESC LIMIT 1
        ) content_label ON true
        WHERE a.brand_id = %s
        ORDER BY coalesce(learning.confirmed_at, learning.completed_at,
                          v.created_at, a.updated_at) DESC
        LIMIT %s
        """,
        (brand["id"], limit),
    ).fetchall()

    result = []
    for row in rows:
        item = dict(row)
        learning_status = item.get("learning_status")
        if learning_status == "confirmed" or item.get("knowledge_version_id"):
            absorption_status = "absorbed"
        elif learning_status in {"ready", "needs_confirmation"}:
            absorption_status = "pending_confirmation"
        elif learning_status == "processing":
            absorption_status = "processing"
        elif learning_status == "forgotten":
            absorption_status = "forgotten"
        elif learning_status == "failed":
            absorption_status = "failed"
        else:
            absorption_status = "not_learned"
        item["absorption_status"] = absorption_status
        if item.get("knowledge_version_id") and not item.get("knowledge_count"):
            item["knowledge_count"] = 1
        result.append(item)
    return result


def get_article(conn: Connection, article_id: UUID) -> dict[str, Any]:
    article = conn.execute(
        "SELECT * FROM xhs_articles WHERE id = %s", (article_id,)
    ).fetchone()
    if not article:
        raise ValueError("文章不存在。")
    versions = conn.execute(
        """
        SELECT id, version_number, version_type, title, body, hashtags, mentioned_products,
               metadata, status, content_hash, knowledge_version_id, created_at
        FROM xhs_article_versions
        WHERE article_id = %s ORDER BY version_number DESC
        """,
        (article_id,),
    ).fetchall()
    interactions = conn.execute(
        """SELECT like_count,collect_count,comment_count,share_count,captured_at,source
           FROM xhs_article_interaction_snapshots WHERE article_id=%s
           ORDER BY captured_at DESC LIMIT 50""", (article_id,)
    ).fetchall()
    # 详情窗口展示最新版本；必须返回理解结果与真实向量数，避免“已入库但前端不可见”。
    images = list_article_images(conn, versions[0]["id"]) if versions else []
    return {"article": article, "versions": versions, "interactions": interactions, "images": images}


def get_article_version(conn: Connection, version_id: UUID) -> dict[str, Any]:
    version = conn.execute(
        """
        SELECT v.*, a.brand_id, a.article_type, a.creator_id, a.creator_name,
               a.creator_type, a.product_code, a.campaign_code, a.content_type,
               a.source_url, a.source_id, b.code AS brand_code, b.name AS brand_name
        FROM xhs_article_versions v
        JOIN xhs_articles a ON a.id = v.article_id
        JOIN brands b ON b.id = a.brand_id
        WHERE v.id = %s
        """,
        (version_id,),
    ).fetchone()
    if not version:
        raise ValueError("文章版本不存在。")
    return version


def approve_article_as_example(
    conn: Connection, version_id: UUID, data: dict[str, Any]
) -> dict[str, Any]:
    """将人工确认的文章版本转换成可检索的正例、反例或竞品参考。"""
    version = get_article_version(conn, version_id)
    if version["status"] in {"active", "approved"} and version["knowledge_version_id"]:
        raise ValueError("该文章版本已经批准为知识案例。")

    article_chunks = conn.execute(
        "SELECT * FROM xhs_article_chunks WHERE article_version_id = %s ORDER BY ordinal",
        (version_id,),
    ).fetchall()
    if not article_chunks:
        raise ValueError("文章没有可用片段。")

    example_kind = data["example_kind"]
    if example_kind == "competitor_reference" and version["article_type"] != "competitor_content":
        raise ValueError("只有竞品文章可以批准为竞品参考。")
    if version["article_type"] == "competitor_content" and example_kind != "competitor_reference":
        raise ValueError("竞品文章只能批准为竞品参考，不能作为本品牌正例或反例。")
    if example_kind == "positive" and version["version_type"] not in {"approved_final", "published"}:
        approved_review = conn.execute(
            """
            SELECT 1 FROM review_cases
            WHERE article_version_id = %s AND overall_decision = 'approve'
            ORDER BY reviewed_at DESC LIMIT 1
            """,
            (version_id,),
        ).fetchone()
        if not approved_review:
            raise ValueError("正例必须是最终批准稿、发布稿，或存在明确的审核通过记录。")
    knowledge_type = (
        "competitor_pattern"
        if version["article_type"] == "competitor_content"
        else "example"
    )
    title_prefix = {
        "positive": "已通过正例",
        "negative": "问题反例",
        "competitor_reference": "竞品参考",
    }[example_kind]
    knowledge = create_knowledge(
        conn,
        {
            "brand_code": version["brand_code"],
            "canonical_key": f"xhs.article.{version['article_id']}.{version['version_number']}",
            "knowledge_type": knowledge_type,
            "title": f"{title_prefix}：{version['title'] or version['article_id']}",
            "summary": data.get("summary") or f"{title_prefix}，来源于真实小红书文章版本。",
            "content": version["normalized_text"],
            "source_version_id": version["source_version_id"],
            "authority_level": data["authority_level"],
            "confidence": data["confidence"],
            "scope": {
                "channels": ["xiaohongshu"],
                "products": [version["product_code"]] if version["product_code"] else [],
                "creator_types": [version["creator_type"]] if version["creator_type"] else [],
                "content_types": [version["content_type"]] if version["content_type"] else [],
                **data.get("scope", {}),
            },
            "attributes": {
                "example_kind": example_kind,
                "article_type": version["article_type"],
                "article_version_id": str(version_id),
                "review_reason": data.get("review_reason"),
            },
            "chunks": [
                {
                    "chunk_type": chunk["chunk_type"],
                    "text": chunk["embedding_text"],
                    "search_terms": chunk["search_terms"],
                    "metadata": {
                        **chunk["metadata"],
                        "original_text": chunk["original_text"],
                        "xhs_article_chunk_id": str(chunk["id"]),
                    },
                }
                for chunk in article_chunks
            ],
        },
    )
    approval = approve_knowledge(
        conn,
        knowledge["version"]["id"],
        {
            "approved_by": data["approved_by"],
            "authority_level": data["authority_level"],
            "confidence": data["confidence"],
            "scope": None,
            "attributes": None,
        },
    )
    conn.execute(
        """
        UPDATE xhs_article_versions
        SET status = 'approved', knowledge_version_id = %s
        WHERE id = %s
        """,
        (knowledge["version"]["id"], version_id),
    )
    knowledge_chunks = conn.execute(
        "SELECT id, metadata FROM kb_chunks WHERE item_version_id = %s",
        (knowledge["version"]["id"],),
    ).fetchall()
    for knowledge_chunk in knowledge_chunks:
        source_chunk_id = knowledge_chunk["metadata"].get("xhs_article_chunk_id")
        if source_chunk_id:
            conn.execute(
                "UPDATE xhs_article_chunks SET kb_chunk_id = %s WHERE id = %s",
                (knowledge_chunk["id"], source_chunk_id),
            )
    return {
        "article_version_id": version_id,
        "knowledge_version_id": knowledge["version"]["id"],
        "example_kind": example_kind,
        **approval,
    }


def submit_article_review(
    conn: Connection, version_id: UUID, data: dict[str, Any]
) -> dict[str, Any]:
    """保存运营经理的审核决定，并把局部修改沉淀成候选经验知识。"""
    version = get_article_version(conn, version_id)
    review_case = conn.execute(
        """
        INSERT INTO review_cases(
            brand_id, source_id, article_version_id, product_code,
            creator_id, creator_type, content_type, campaign_code,
            overall_decision, reviewer, reviewed_at, context
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), %s::jsonb)
        RETURNING id
        """,
        (
            version["brand_id"], version["source_id"], version_id,
            version["product_code"], version["creator_id"], version["creator_type"],
            version["content_type"], version["campaign_code"],
            data["overall_decision"], data["reviewer"],
            json.dumps(data.get("context", {}), ensure_ascii=False),
        ),
    ).fetchone()
    review_content = conn.execute(
        """
        INSERT INTO review_content_versions(
            review_case_id, version_number, version_type, title, body, content_hash
        ) VALUES (%s, 1, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            review_case["id"], version["version_type"], version["title"],
            version["body"], version["content_hash"],
        ),
    ).fetchone()

    annotation_ids: list[UUID] = []
    candidate_version_ids: list[UUID] = []
    for annotation in data.get("annotations", []):
        row = conn.execute(
            """
            INSERT INTO review_annotations(
                review_case_id, content_version_id, location_type, location_data,
                original_text, revised_text, decision, reason, reason_codes,
                severity, reviewer_confidence, linked_rule_version_id
            ) VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                review_case["id"], review_content["id"], annotation["location_type"],
                json.dumps(annotation.get("location_data", {}), ensure_ascii=False),
                annotation.get("original_text"), annotation.get("revised_text"),
                annotation["decision"], annotation["reason"], annotation.get("reason_codes", []),
                annotation.get("severity"), annotation.get("reviewer_confidence"),
                annotation.get("linked_rule_version_id"),
            ),
        ).fetchone()
        annotation_ids.append(row["id"])

        if data.get("distill_annotations", True):
            text_parts = [
                f"审核原文：{annotation.get('original_text')}" if annotation.get("original_text") else "",
                f"建议改为：{annotation.get('revised_text')}" if annotation.get("revised_text") else "",
                f"审核原因：{annotation['reason']}",
            ]
            distilled_content = "\n".join(part for part in text_parts if part)
            knowledge = create_knowledge(
                conn,
                {
                    "brand_code": version["brand_code"],
                    "canonical_key": f"review.annotation.{row['id']}",
                    "knowledge_type": "review_annotation",
                    "title": f"审核经验：{annotation['reason'][:50]}",
                    "summary": annotation["reason"],
                    "content": distilled_content,
                    "source_version_id": version["source_version_id"],
                    "authority_level": 2,
                    "confidence": annotation.get("reviewer_confidence"),
                    "scope": {
                        "channels": ["xiaohongshu"],
                        "products": [version["product_code"]] if version["product_code"] else [],
                        "creator_types": [version["creator_type"]] if version["creator_type"] else [],
                        "content_types": [version["content_type"]] if version["content_type"] else [],
                    },
                    "attributes": {
                        "review_case_id": str(review_case["id"]),
                        "annotation_id": str(row["id"]),
                        "reason_codes": annotation.get("reason_codes", []),
                        "decision": annotation["decision"],
                        "severity": annotation.get("severity"),
                    },
                    "chunks": [
                        *([{
                            "chunk_type": "review_original",
                            "text": annotation["original_text"],
                            "search_terms": "",
                            "metadata": {},
                        }] if annotation.get("original_text") else []),
                        *([{
                            "chunk_type": "review_revision",
                            "text": annotation["revised_text"],
                            "search_terms": "",
                            "metadata": {},
                        }] if annotation.get("revised_text") else []),
                        {
                            "chunk_type": "reason",
                            "text": annotation["reason"],
                            "search_terms": "",
                            "metadata": {"reason_codes": annotation.get("reason_codes", [])},
                        },
                    ],
                },
            )
            candidate_version_ids.append(knowledge["version"]["id"])
            conn.execute(
                "UPDATE review_annotations SET distilled_knowledge_version_id = %s WHERE id = %s",
                (knowledge["version"]["id"], row["id"]),
            )

    conn.execute(
        "UPDATE xhs_article_versions SET status = %s WHERE id = %s",
        ("rejected" if data["overall_decision"] == "reject" else "reviewed", version_id),
    )
    return {
        "review_case_id": review_case["id"],
        "annotation_ids": annotation_ids,
        "candidate_knowledge_version_ids": candidate_version_ids,
    }
