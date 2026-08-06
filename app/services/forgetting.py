"""文章知识遗忘：保留原始素材，只撤销它派生出的可检索知识。"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from psycopg import Connection


def _scope(conn: Connection, article_id: UUID) -> dict[str, Any]:
    article = conn.execute(
        "SELECT id, brand_id FROM xhs_articles WHERE id=%s", (article_id,)
    ).fetchone()
    if not article:
        raise ValueError("文章不存在。")
    sessions = conn.execute(
        """SELECT DISTINCT s.id
           FROM xhs_learning_sessions s
           JOIN xhs_article_versions v ON v.id IN (
               s.original_article_version_id, s.revised_article_version_id
           )
           WHERE v.article_id=%s AND s.status <> 'forgotten'""",
        (article_id,),
    ).fetchall()
    session_ids = [row["id"] for row in sessions]
    article_version_ids = [row["id"] for row in conn.execute(
        "SELECT id FROM xhs_article_versions WHERE article_id=%s", (article_id,),
    ).fetchall()]
    knowledge_rows = conn.execute(
        """SELECT DISTINCT knowledge_version_id AS id
           FROM xhs_learning_insights
           WHERE session_id=ANY(%s) AND knowledge_version_id IS NOT NULL
           UNION
           SELECT DISTINCT knowledge_version_id AS id
           FROM xhs_article_versions
           WHERE article_id=%s AND knowledge_version_id IS NOT NULL""",
        (session_ids, article_id),
    ).fetchall() if session_ids else conn.execute(
        """SELECT DISTINCT knowledge_version_id AS id FROM xhs_article_versions
           WHERE article_id=%s AND knowledge_version_id IS NOT NULL""", (article_id,)
    ).fetchall()
    knowledge_ids = [row["id"] for row in knowledge_rows]
    chunks = conn.execute(
        "SELECT id FROM kb_chunks WHERE item_version_id=ANY(%s)", (knowledge_ids,)
    ).fetchall() if knowledge_ids else []
    chunk_ids = [row["id"] for row in chunks]
    vector_count = conn.execute(
        "SELECT count(*) AS count FROM kb_text_embeddings WHERE chunk_id=ANY(%s)",
        (chunk_ids,),
    ).fetchone()["count"] if chunk_ids else 0
    job_count = conn.execute(
        "SELECT count(*) AS count FROM kb_jobs WHERE entity_id=ANY(%s)", (chunk_ids,)
    ).fetchone()["count"] if chunk_ids else 0
    insight_count = conn.execute(
        "SELECT count(*) AS count FROM xhs_learning_insights WHERE session_id=ANY(%s)",
        (session_ids,),
    ).fetchone()["count"] if session_ids else 0
    affected_articles = conn.execute(
        """SELECT count(DISTINCT v.article_id) AS count
           FROM xhs_article_versions v
           JOIN xhs_learning_sessions s ON v.id IN (
               s.original_article_version_id, s.revised_article_version_id
           ) WHERE s.id=ANY(%s)""", (session_ids,)
    ).fetchone()["count"] if session_ids else 1
    multimodal_vector_count = conn.execute(
        "SELECT count(*) AS count FROM kb_multimodal_embeddings WHERE article_version_id=ANY(%s)",
        (article_version_ids,),
    ).fetchone()["count"] if article_version_ids else 0
    image_analysis_count = conn.execute(
        "SELECT count(*) AS count FROM xhs_image_analyses WHERE article_version_id=ANY(%s)",
        (article_version_ids,),
    ).fetchone()["count"] if article_version_ids else 0
    return {
        "article": article, "session_ids": session_ids, "knowledge_ids": knowledge_ids,
        "chunk_ids": chunk_ids, "insight_count": insight_count,
        "vector_count": vector_count, "job_count": job_count,
        "affected_article_count": affected_articles, "article_version_ids": article_version_ids,
        "multimodal_vector_count": multimodal_vector_count, "image_analysis_count": image_analysis_count,
    }


def preview_forget_article_knowledge(conn: Connection, article_id: UUID) -> dict[str, Any]:
    scope = _scope(conn, article_id)
    return {
        "article_id": article_id,
        "can_forget": bool(scope["session_ids"] or scope["knowledge_ids"]),
        "original_article_retained": True,
        "images_retained": True,
        "learning_session_count": len(scope["session_ids"]),
        "insight_count": scope["insight_count"],
        "knowledge_version_count": len(scope["knowledge_ids"]),
        "chunk_count": len(scope["chunk_ids"]),
        "vector_count": scope["vector_count"],
        "job_count": scope["job_count"],
        "image_analysis_count": scope["image_analysis_count"],
        "multimodal_vector_count": scope["multimodal_vector_count"],
        "affected_article_count": scope["affected_article_count"],
    }


def forget_article_knowledge(
    conn: Connection, article_id: UUID, forgotten_by: str, reason: str | None = None
) -> dict[str, Any]:
    scope = _scope(conn, article_id)
    session_ids = scope["session_ids"]
    knowledge_ids = scope["knowledge_ids"]
    chunk_ids = scope["chunk_ids"]
    if not session_ids and not knowledge_ids:
        return {**preview_forget_article_knowledge(conn, article_id), "status": "already_forgotten"}

    # 只删除没有被其他文章、审核记录或知识版本引用的知识版本。
    deletable_rows = conn.execute(
        """SELECT candidate.id FROM unnest(%s::uuid[]) candidate(id)
           WHERE NOT EXISTS (SELECT 1 FROM xhs_article_versions v
                             WHERE v.knowledge_version_id=candidate.id AND v.article_id<>%s)
             AND NOT EXISTS (SELECT 1 FROM xhs_learning_insights i
                             WHERE i.knowledge_version_id=candidate.id AND NOT (i.session_id=ANY(%s)))
             AND NOT EXISTS (SELECT 1 FROM review_annotations r
                             WHERE r.linked_rule_version_id=candidate.id OR r.distilled_knowledge_version_id=candidate.id)
             AND NOT EXISTS (SELECT 1 FROM kb_asset_annotations a WHERE a.item_version_id=candidate.id)
             AND NOT EXISTS (SELECT 1 FROM kb_item_versions v WHERE v.supersedes_version_id=candidate.id)""",
        (knowledge_ids, article_id, session_ids),
    ).fetchall() if knowledge_ids else []
    deletable_ids = [row["id"] for row in deletable_rows]
    deletable_chunks = conn.execute(
        "SELECT id FROM kb_chunks WHERE item_version_id=ANY(%s)", (deletable_ids,)
    ).fetchall() if deletable_ids else []
    deletable_chunk_ids = [row["id"] for row in deletable_chunks]

    deleted_jobs = len(conn.execute(
        "DELETE FROM kb_jobs WHERE entity_id=ANY(%s) RETURNING id", (deletable_chunk_ids,)
    ).fetchall()) if deletable_chunk_ids else 0
    deleted_vectors = len(conn.execute(
        "DELETE FROM kb_text_embeddings WHERE chunk_id=ANY(%s) RETURNING id", (deletable_chunk_ids,)
    ).fetchall()) if deletable_chunk_ids else 0
    deleted_multimodal_vectors = len(conn.execute(
        "DELETE FROM kb_multimodal_embeddings WHERE article_version_id=ANY(%s) RETURNING id",
        (scope["article_version_ids"],),
    ).fetchall()) if scope["article_version_ids"] else 0
    deleted_image_analyses = len(conn.execute(
        "DELETE FROM xhs_image_analyses WHERE article_version_id=ANY(%s) RETURNING id",
        (scope["article_version_ids"],),
    ).fetchall()) if scope["article_version_ids"] else 0
    if scope["article_version_ids"]:
        conn.execute(
            """DELETE FROM kb_jobs WHERE job_type IN ('analyze_image','embed_image')
               AND payload->>'article_version_id'=ANY(%s)""",
            ([str(value) for value in scope["article_version_ids"]],),
        )
    deleted_chunks = len(conn.execute(
        "DELETE FROM kb_chunks WHERE id=ANY(%s) RETURNING id", (deletable_chunk_ids,)
    ).fetchall()) if deletable_chunk_ids else 0

    conn.execute(
        "UPDATE xhs_article_versions SET knowledge_version_id=NULL WHERE article_id=%s",
        (article_id,),
    )
    if session_ids:
        conn.execute(
            "DELETE FROM xhs_learning_insights WHERE session_id=ANY(%s)", (session_ids,)
        )
        conn.execute(
            """UPDATE xhs_learning_sessions
               SET status='forgotten', input_hash=NULL, analysis_summary=NULL,
                   raw_analysis='{}'::jsonb, error_message=NULL,
                   forgotten_at=now(), forgotten_by=%s
               WHERE id=ANY(%s)""",
            (forgotten_by, session_ids),
        )

    deleted_versions = []
    item_ids = []
    if deletable_ids:
        item_ids = [row["item_id"] for row in conn.execute(
            "SELECT DISTINCT item_id FROM kb_item_versions WHERE id=ANY(%s)", (deletable_ids,)
        ).fetchall()]
        deleted_versions = [row["id"] for row in conn.execute(
            "DELETE FROM kb_item_versions WHERE id=ANY(%s) RETURNING id", (deletable_ids,)
        ).fetchall()]
    if item_ids:
        conn.execute(
            """DELETE FROM kb_items item WHERE id=ANY(%s)
               AND NOT EXISTS (SELECT 1 FROM kb_item_versions version WHERE version.item_id=item.id)""",
            (item_ids,),
        )

    summary = {
        "sessions_forgotten": len(session_ids), "insights_deleted": scope["insight_count"],
        "knowledge_versions_deleted": len(deleted_versions),
        "shared_knowledge_retained": len(knowledge_ids) - len(deleted_versions),
        "chunks_deleted": deleted_chunks, "vectors_deleted": deleted_vectors,
        "jobs_deleted": deleted_jobs,
        "image_analyses_deleted": deleted_image_analyses,
        "multimodal_vectors_deleted": deleted_multimodal_vectors,
    }
    event = conn.execute(
        """INSERT INTO xhs_article_forget_events(
               article_id, brand_id, forgotten_by, reason, affected_session_ids,
               affected_knowledge_version_ids, deletion_summary
           ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb) RETURNING id, created_at""",
        (article_id, scope["article"]["brand_id"], forgotten_by, reason,
         session_ids, knowledge_ids, json.dumps(summary, ensure_ascii=False)),
    ).fetchone()
    return {
        "status": "forgotten", "article_id": article_id,
        "original_article_retained": True, "images_retained": True,
        "event_id": event["id"], "forgotten_at": event["created_at"], **summary,
    }


def preview_delete_article(conn: Connection, article_id: UUID) -> dict[str, Any]:
    """预览永久删除影响；向量范围沿用经过共享引用保护的知识遗忘逻辑。"""
    scope = _scope(conn, article_id)
    article = conn.execute(
        """SELECT a.id, a.brand_id,
                  coalesce((array_agg(v.title ORDER BY v.version_number DESC))[1], '未命名文章') AS title,
                  count(DISTINCT v.id)::int AS version_count
           FROM xhs_articles a LEFT JOIN xhs_article_versions v ON v.article_id=a.id
           WHERE a.id=%s GROUP BY a.id, a.brand_id""", (article_id,),
    ).fetchone()
    image_count = conn.execute(
        """SELECT count(*)::int AS count FROM xhs_article_assets link
           JOIN xhs_article_versions v ON v.id=link.article_version_id
           WHERE v.article_id=%s""", (article_id,),
    ).fetchone()["count"]
    knowledge_preview = preview_forget_article_knowledge(conn, article_id)
    return {**knowledge_preview, "article_title": article["title"],
            "version_count": article["version_count"], "image_link_count": image_count,
            "article_will_be_deleted": True, "recoverable": False,
            "affected_article_count": scope["affected_article_count"]}


def delete_article_with_knowledge(
    conn: Connection, article_id: UUID, deleted_by: str, reason: str | None = None
) -> dict[str, Any]:
    """在同一事务内永久删除文章，并安全回退其非共享知识和向量。"""
    preview = preview_delete_article(conn, article_id)
    scope = _scope(conn, article_id)
    rollback = forget_article_knowledge(conn, article_id, deleted_by, reason or "永久删除文章")
    session_ids = scope["session_ids"]
    if session_ids:
        conn.execute("DELETE FROM xhs_learning_sessions WHERE id=ANY(%s)", (session_ids,))
    # 保留审核与批次审计记录，但解除它们对即将删除原文的外键引用。
    conn.execute(
        """UPDATE review_cases SET article_version_id=NULL
           WHERE article_version_id IN (SELECT id FROM xhs_article_versions WHERE article_id=%s)""",
        (article_id,),
    )
    conn.execute(
        """UPDATE xhs_ingestion_items SET article_id=NULL, article_version_id=NULL
           WHERE article_id=%s OR article_version_id IN
                 (SELECT id FROM xhs_article_versions WHERE article_id=%s)""",
        (article_id, article_id),
    )
    deleted = conn.execute(
        "DELETE FROM xhs_articles WHERE id=%s RETURNING id, brand_id", (article_id,)
    ).fetchone()
    if not deleted:
        raise ValueError("文章不存在。")
    summary = {
        "article_versions_deleted": preview["version_count"],
        "image_links_deleted": preview["image_link_count"],
        "learning_sessions_deleted": len(session_ids),
        "knowledge_versions_deleted": rollback.get("knowledge_versions_deleted", 0),
        "shared_knowledge_retained": rollback.get("shared_knowledge_retained", 0),
        "chunks_deleted": rollback.get("chunks_deleted", 0),
        "vectors_deleted": rollback.get("vectors_deleted", 0),
        "jobs_deleted": rollback.get("jobs_deleted", 0),
    }
    event = conn.execute(
        """INSERT INTO xhs_article_deletion_events(
               article_id, brand_id, article_title, deleted_by, reason, deletion_summary
           ) VALUES (%s,%s,%s,%s,%s,%s::jsonb) RETURNING id, created_at""",
        (article_id, deleted["brand_id"], preview["article_title"], deleted_by, reason,
         json.dumps(summary, ensure_ascii=False)),
    ).fetchone()
    return {"status": "deleted", "article_id": article_id, "recoverable": False,
            "event_id": event["id"], "deleted_at": event["created_at"], **summary}
