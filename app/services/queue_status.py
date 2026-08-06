"""面向前端的学习与向量化队列状态。"""

from __future__ import annotations

from typing import Any

from psycopg import Connection

from app.services.knowledge import get_brand


def _display_state(row: dict[str, Any]) -> tuple[str, int, str]:
    learning_status = row["learning_status"]
    if learning_status == "failed":
        return "analysis_failed", 0, "AI分析失败"
    if learning_status == "processing":
        return "analyzing", 20, "AI正在分析"
    if learning_status in {"ready", "needs_confirmation"}:
        return "awaiting_confirmation", 45, "等待确认吸收"
    if learning_status != "confirmed":
        return "preparing", 10, "正在准备"
    if row["failed_jobs"]:
        return "vector_failed", 70, "向量化失败"
    chunk_count = int(row["chunk_count"] or 0)
    embedding_count = int(row["embedding_count"] or 0)
    if chunk_count and embedding_count >= chunk_count:
        return "vectorized", 100, "已进入向量库"
    if row["running_jobs"]:
        ratio = embedding_count / chunk_count if chunk_count else 0
        return "vectorizing", min(95, 60 + round(ratio * 35)), "正在向量化"
    if row["pending_jobs"]:
        return "queued", 60, "等待向量化"
    return "confirmed", 55, "已确认，正在生成任务"


def get_learning_queue(conn: Connection, brand_code: str, limit: int = 30) -> dict[str, Any]:
    """以真实Embedding记录作为“进入向量库”的最终判定依据。"""
    brand = get_brand(conn, brand_code)
    rows = conn.execute(
        """
        SELECT ls.id, ls.learning_mode, ls.status::text AS learning_status,
               ls.analysis_summary, ls.error_message, ls.created_at,
               ls.completed_at, ls.confirmed_at,
               coalesce(nullif(av.title, ''), nullif(rv.title, ''), '口述运营经验') AS title,
               coalesce(av.creator_name, rv.creator_name) AS creator_name,
               queue.insight_count, queue.knowledge_count, queue.chunk_count,
               queue.embedding_count, queue.pending_jobs, queue.running_jobs,
               queue.succeeded_jobs, queue.failed_jobs,
               queue.last_job_error, queue.last_job_updated_at
        FROM xhs_learning_sessions ls
        LEFT JOIN LATERAL (
            SELECT v.title, a.creator_name
            FROM xhs_article_versions v
            JOIN xhs_articles a ON a.id = v.article_id
            WHERE v.id = ls.original_article_version_id
        ) av ON true
        LEFT JOIN LATERAL (
            SELECT v.title, a.creator_name
            FROM xhs_article_versions v
            JOIN xhs_articles a ON a.id = v.article_id
            WHERE v.id = ls.revised_article_version_id
        ) rv ON true
        LEFT JOIN LATERAL (
            SELECT count(DISTINCT li.id)::int AS insight_count,
                   count(DISTINCT li.knowledge_version_id)::int AS knowledge_count,
                   count(DISTINCT chunk.id)::int AS chunk_count,
                   count(DISTINCT embedding.chunk_id)::int AS embedding_count,
                   count(DISTINCT job.id) FILTER (WHERE job.status='pending')::int AS pending_jobs,
                   count(DISTINCT job.id) FILTER (WHERE job.status='running')::int AS running_jobs,
                   count(DISTINCT job.id) FILTER (WHERE job.status='succeeded')::int AS succeeded_jobs,
                   count(DISTINCT job.id) FILTER (WHERE job.status='failed')::int AS failed_jobs,
                   max(job.last_error) FILTER (WHERE job.status='failed') AS last_job_error,
                   max(job.updated_at) AS last_job_updated_at
            FROM xhs_learning_insights li
            LEFT JOIN kb_chunks chunk ON chunk.item_version_id = li.knowledge_version_id
            LEFT JOIN kb_text_embeddings embedding ON embedding.chunk_id = chunk.id
            LEFT JOIN kb_jobs job
              ON job.entity_id = chunk.id AND job.job_type = 'embed_chunk'
            WHERE li.session_id = ls.id
        ) queue ON true
        WHERE ls.brand_id = %s
        ORDER BY ls.created_at DESC
        LIMIT %s
        """,
        (brand["id"], limit),
    ).fetchall()

    items = []
    for record in rows:
        item = dict(record)
        state, progress, state_label = _display_state(item)
        item.update({"state": state, "progress": progress, "state_label": state_label})
        items.append(item)

    # 后台连续导入在创建学习会话前也必须可见，否则会出现“顶部有任务、列表为空”。
    background_jobs = conn.execute(
        """SELECT id,status::text AS job_status,payload,last_error,created_at,updated_at
           FROM kb_jobs
           WHERE brand_id=%s AND job_type='ingest_learning'
             AND status IN ('pending','running','failed')
           ORDER BY created_at DESC LIMIT %s""",
        (brand["id"], limit),
    ).fetchall()
    for record in background_jobs:
        payload = record["payload"] or {}
        learning_data = payload.get("learning_data") or {}
        article = learning_data.get("revised_article") or learning_data.get("original_article") or {}
        job_status = record["job_status"]
        if job_status == "pending":
            state, progress, label = "queued", 5, "等待AI分析"
        elif job_status == "running":
            state, progress, label = "analyzing", 15, "AI正在后台分析"
        else:
            state, progress, label = "analysis_failed", 0, "后台任务失败"
        items.append({
            "id": record["id"], "learning_mode": learning_data.get("learning_mode"),
            "learning_status": "processing" if job_status != "failed" else "failed",
            "title": article.get("title") or (learning_data.get("user_feedback") or "口述运营经验")[:60],
            "creator_name": article.get("creator_name") or learning_data.get("created_by"),
            "created_at": record["created_at"], "completed_at": None, "confirmed_at": None,
            "insight_count": 0, "knowledge_count": 0, "chunk_count": 0, "embedding_count": 0,
            "pending_jobs": 1 if job_status == "pending" else 0,
            "running_jobs": 1 if job_status == "running" else 0,
            "failed_jobs": 1 if job_status == "failed" else 0,
            "last_job_error": record["last_error"], "state": state,
            "progress": progress, "state_label": label, "is_background_request": True,
        })
    items.sort(key=lambda item: item.get("created_at"), reverse=True)
    items = items[:limit]

    job_summary = conn.execute(
        """
        SELECT count(*) FILTER (WHERE status='pending')::int AS pending,
               count(*) FILTER (WHERE status='running')::int AS running,
               count(*) FILTER (WHERE status='succeeded')::int AS succeeded,
               count(*) FILTER (WHERE status='failed')::int AS failed
        FROM kb_jobs WHERE brand_id = %s AND job_type IN ('ingest_learning','embed_chunk','analyze_image','embed_image')
        """,
        (brand["id"],),
    ).fetchone()
    vector_count = conn.execute(
        "SELECT count(*)::int AS n FROM kb_text_embeddings WHERE brand_id=%s",
        (brand["id"],),
    ).fetchone()["n"]
    image_summary = conn.execute(
        """SELECT count(*) FILTER (WHERE status='succeeded')::int AS understood,
                  count(*) FILTER (WHERE status='failed')::int AS failed
           FROM xhs_image_analyses WHERE brand_id=%s""", (brand["id"],),
    ).fetchone()
    multimodal_vector_count = conn.execute(
        "SELECT count(*)::int AS n FROM kb_multimodal_embeddings WHERE brand_id=%s AND active=true",
        (brand["id"],),
    ).fetchone()["n"]
    return {
        "summary": {
            **dict(job_summary),
            "vector_count": vector_count,
            "images_understood": image_summary["understood"],
            "image_analysis_failed": image_summary["failed"],
            "multimodal_vector_count": multimodal_vector_count,
            "active_items": sum(item["state"] not in {"vectorized", "analysis_failed", "vector_failed"} for item in items),
        },
        "items": items,
    }
