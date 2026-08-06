"""数据库后台任务工作进程。

使用 PostgreSQL 的 FOR UPDATE SKIP LOCKED 安全领取任务，支持启动多个进程。
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time

from app.config import settings
from app.db import close_pool, open_pool, transaction
from app.services.embedding import embed_text
from app.services.assets import ingest_article_images, resolve_asset_path
from app.services.learning import confirm_learning_session, create_learning_session
from app.services.multimodal import analyze_image, analysis_embedding_text, embed_multimodal


WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.9g}" for value in vector) + "]"


def process_ingest_learning(job: dict) -> None:
    """后台完成分析、自动确认和图片入库，使前端可立即开始下一次导入。"""
    data = job["payload"]["learning_data"]
    with transaction() as conn:
        result = create_learning_session(conn, data)
    session = result["session"]
    if session["status"] == "failed":
        # 会话已保留失败原因，队列中心可以向用户展示。
        return
    version_id = session.get("original_article_version_id")
    if version_id and not result.get("deduplicated"):
        with transaction() as conn:
            ingest_article_images(conn, version_id)
    if job["payload"].get("auto_confirm") and session["status"] in {"ready", "needs_confirmation"}:
        with transaction() as conn:
            confirm_learning_session(conn, session["id"], {
                "confirmed_by": data.get("created_by") or "本地运营用户",
                "publish_to_retrieval": True,
                "rejected_insight_ids": [],
                "corrections": [],
            })


def claim_job() -> dict | None:
    with transaction() as conn:
        job = conn.execute(
            """
            SELECT id, brand_id, job_type, entity_type, entity_id,
                   payload, attempts, max_attempts
            FROM kb_jobs
            WHERE status = 'pending' AND available_at <= now()
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """
        ).fetchone()
        if not job:
            return None
        conn.execute(
            """
            UPDATE kb_jobs
            SET status = 'running', locked_at = now(), locked_by = %s,
                attempts = attempts + 1, updated_at = now()
            WHERE id = %s
            """,
            (WORKER_ID, job["id"]),
        )
        return job


def process_embed_chunk(job: dict) -> None:
    with transaction() as conn:
        chunk = conn.execute(
            "SELECT id, brand_id, item_version_id, text, content_hash FROM kb_chunks WHERE id = %s",
            (job["entity_id"],),
        ).fetchone()
        if not chunk:
            raise RuntimeError("待向量化知识片段不存在。")
        model_id = job["payload"]["model_id"]

    input_hash = hashlib.sha256(
        f"{model_id}:{chunk['content_hash']}".encode("utf-8")
    ).hexdigest()
    vector = embed_text(chunk["text"], input_type="document")

    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO kb_text_embeddings(
                brand_id, chunk_id, model_id, embedding, input_hash
            ) VALUES (%s, %s, %s, %s::halfvec(1536), %s)
            ON CONFLICT (chunk_id, model_id, input_hash) DO NOTHING
            """,
            (
                chunk["brand_id"], chunk["id"], model_id,
                _vector_literal(vector), input_hash,
            ),
        )
        remaining = conn.execute(
            """
            SELECT count(*) AS n
            FROM kb_chunks c
            LEFT JOIN kb_text_embeddings e
              ON e.chunk_id = c.id AND e.model_id = %s
            WHERE c.item_version_id = %s AND e.id IS NULL
            """,
            (model_id, chunk["item_version_id"]),
        ).fetchone()["n"]
        if remaining == 0:
            activate_version(conn, chunk["item_version_id"])


def _score(value) -> float | None:
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return None


def process_analyze_image(job: dict) -> None:
    article_version_id = job["payload"]["article_version_id"]
    ordinal = int(job["payload"].get("ordinal", 0))
    with transaction() as conn:
        row = conn.execute(
            """SELECT asset.id AS asset_id, asset.mime_type, article.brand_id,
                      version.title, version.body
               FROM kb_assets asset JOIN xhs_article_assets link ON link.asset_id=asset.id
               JOIN xhs_article_versions version ON version.id=link.article_version_id
               JOIN xhs_articles article ON article.id=version.article_id
               WHERE asset.id=%s AND version.id=%s""", (job["entity_id"], article_version_id),
        ).fetchone()
        if not row:
            raise RuntimeError("待分析图片或文章版本不存在。")
        path, mime_type = resolve_asset_path(conn, row["asset_id"])
    raw = analyze_image(path, mime_type, row["title"] or "", row["body"] or "")
    with transaction() as conn:
        analysis = conn.execute(
            """INSERT INTO xhs_image_analyses(
                 brand_id,asset_id,article_version_id,ordinal,status,model_name,prompt_version,
                 asset_role,visual_type,summary,ocr_text,objects,product_exposure,aesthetic,
                 content_functions,brand_fit_score,cover_click_score,selling_power_score,
                 compliance_risks,evidence,reusable_visual_rules,confidence,raw_analysis,completed_at)
               VALUES (%s,%s,%s,%s,'succeeded',%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,
                 %s::jsonb,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s::jsonb,now())
               ON CONFLICT(asset_id,article_version_id,prompt_version) DO UPDATE SET
                 status='succeeded',model_name=excluded.model_name,asset_role=excluded.asset_role,
                 visual_type=excluded.visual_type,summary=excluded.summary,ocr_text=excluded.ocr_text,
                 objects=excluded.objects,product_exposure=excluded.product_exposure,aesthetic=excluded.aesthetic,
                 content_functions=excluded.content_functions,brand_fit_score=excluded.brand_fit_score,
                 cover_click_score=excluded.cover_click_score,selling_power_score=excluded.selling_power_score,
                 compliance_risks=excluded.compliance_risks,evidence=excluded.evidence,
                 reusable_visual_rules=excluded.reusable_visual_rules,confidence=excluded.confidence,
                 raw_analysis=excluded.raw_analysis,error_message=NULL,completed_at=now() RETURNING id""",
            (row["brand_id"],row["asset_id"],article_version_id,ordinal,settings.vision_model,
             settings.vision_prompt_version,raw.get("asset_role"),raw.get("visual_type"),raw.get("summary"),
             raw.get("ocr_text"),json.dumps(raw.get("objects",[]),ensure_ascii=False),
             json.dumps(raw.get("product_exposure",{}),ensure_ascii=False),json.dumps(raw.get("aesthetic",{}),ensure_ascii=False),
             json.dumps(raw.get("content_functions",[]),ensure_ascii=False),_score(raw.get("brand_fit_score")),
             _score(raw.get("cover_click_score")),_score(raw.get("selling_power_score")),
             json.dumps(raw.get("compliance_risks",[]),ensure_ascii=False),json.dumps(raw.get("evidence",[]),ensure_ascii=False),
             json.dumps(raw.get("reusable_visual_rules",[]),ensure_ascii=False),_score(raw.get("confidence")),
             json.dumps(raw,ensure_ascii=False)),
        ).fetchone()
        conn.execute(
            """INSERT INTO kb_jobs(brand_id,job_type,entity_type,entity_id,payload,max_attempts)
               VALUES (%s,'embed_image','asset',%s,%s::jsonb,3)""",
            (row["brand_id"],row["asset_id"],json.dumps({"article_version_id":str(article_version_id),"analysis_id":str(analysis["id"])})),
        )


def process_embed_image(job: dict) -> None:
    article_version_id = job["payload"]["article_version_id"]
    with transaction() as conn:
        row = conn.execute(
            """SELECT asset.id AS asset_id, asset.content_hash, article.brand_id,
                      version.title,version.body,analysis.id AS analysis_id,analysis.raw_analysis
               FROM kb_assets asset JOIN xhs_article_assets link ON link.asset_id=asset.id
               JOIN xhs_article_versions version ON version.id=link.article_version_id
               JOIN xhs_articles article ON article.id=version.article_id
               JOIN xhs_image_analyses analysis ON analysis.asset_id=asset.id AND analysis.article_version_id=version.id
               WHERE asset.id=%s AND version.id=%s""", (job["entity_id"],article_version_id),
        ).fetchone()
        if not row:
            raise RuntimeError("图片理解结果不存在。")
        path,mime_type=resolve_asset_path(conn,row["asset_id"])
    representations=[("image","independent",None),
                     ("image_text_fusion","fused",analysis_embedding_text(row["raw_analysis"],row["title"] or "",row["body"] or ""))]
    for modality,kind,text in representations:
        vector=embed_multimodal(path,mime_type,text)
        input_hash=hashlib.sha256(f"{settings.multimodal_embedding_model}:{row['content_hash']}:{text or ''}".encode()).hexdigest()
        with transaction() as conn:
            conn.execute(
                """INSERT INTO kb_multimodal_embeddings(
                     brand_id,article_version_id,asset_id,analysis_id,modality,representation_type,
                     model_name,dimensions,embedding,input_hash)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,1536,%s::halfvec(1536),%s)
                   ON CONFLICT(asset_id,article_version_id,modality,model_name,input_hash) DO NOTHING""",
                (row["brand_id"],article_version_id,row["asset_id"],row["analysis_id"],modality,kind,
                 settings.multimodal_embedding_model,_vector_literal(vector),input_hash),
            )


def activate_version(conn, version_id) -> None:
    version = conn.execute(
        "SELECT id, item_id, status FROM kb_item_versions WHERE id = %s FOR UPDATE",
        (version_id,),
    ).fetchone()
    if not version or version["status"] not in {"reviewed", "active"}:
        return
    conn.execute(
        """
        UPDATE kb_chunks SET active = false
        WHERE item_version_id IN (
            SELECT id FROM kb_item_versions
            WHERE item_id = %s AND id <> %s
        )
        """,
        (version["item_id"], version_id),
    )
    conn.execute(
        """
        UPDATE kb_item_versions
        SET status = 'superseded', valid_to = now()
        WHERE item_id = %s AND id <> %s AND status = 'active'
        """,
        (version["item_id"], version_id),
    )
    conn.execute(
        """
        UPDATE kb_item_versions
        SET status = 'active', valid_from = coalesce(valid_from, now()), valid_to = NULL
        WHERE id = %s
        """,
        (version_id,),
    )
    conn.execute("UPDATE kb_chunks SET active = true WHERE item_version_id = %s", (version_id,))
    # 如果该知识版本来自已批准的小红书文章，同步激活文章版本与原始结构片段。
    conn.execute(
        "UPDATE xhs_article_versions SET status = 'active' WHERE knowledge_version_id = %s",
        (version_id,),
    )
    conn.execute(
        """
        UPDATE xhs_article_chunks SET active = true
        WHERE article_version_id IN (
            SELECT id FROM xhs_article_versions WHERE knowledge_version_id = %s
        )
        """,
        (version_id,),
    )


def finish_job(job_id) -> None:
    with transaction() as conn:
        conn.execute(
            "UPDATE kb_jobs SET status = 'succeeded', updated_at = now() WHERE id = %s",
            (job_id,),
        )


def fail_job(job: dict, exc: Exception) -> None:
    attempts_after_claim = job["attempts"] + 1
    should_retry = attempts_after_claim < job["max_attempts"]
    with transaction() as conn:
        conn.execute(
            """
            UPDATE kb_jobs
            SET status = %s::job_status,
                available_at = CASE WHEN %s THEN now() + make_interval(secs => %s) ELSE available_at END,
                last_error = %s, locked_at = NULL, locked_by = NULL, updated_at = now()
            WHERE id = %s
            """,
            (
                "pending" if should_retry else "failed",
                should_retry,
                min(300, 2 ** attempts_after_claim),
                str(exc)[:2000],
                job["id"],
            ),
        )


def run_forever() -> None:
    open_pool()
    print(f"知识库后台任务已启动：{WORKER_ID}")
    try:
        while True:
            job = claim_job()
            if not job:
                time.sleep(settings.job_poll_seconds)
                continue
            try:
                if job["job_type"] == "embed_chunk":
                    process_embed_chunk(job)
                elif job["job_type"] == "ingest_learning":
                    process_ingest_learning(job)
                elif job["job_type"] == "analyze_image":
                    process_analyze_image(job)
                elif job["job_type"] == "embed_image":
                    process_embed_image(job)
                else:
                    raise RuntimeError(f"暂不支持的任务类型：{job['job_type']}")
                finish_job(job["id"])
            except Exception as exc:
                print(f"任务失败 {job['id']}：{exc}")
                fail_job(job, exc)
    finally:
        close_pool()


if __name__ == "__main__":
    run_forever()
