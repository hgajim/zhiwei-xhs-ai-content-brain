"""混合检索服务：向量检索 + 关键词检索 + RRF 融合。"""

from __future__ import annotations

import json
from typing import Any

from psycopg import Connection

from app.services.embedding import embed_text
from app.services.chunking import segment_for_search
from app.services.knowledge import get_brand


def _vector_literal(vector: list[float]) -> str:
    """将向量转成 pgvector/halfvec 可接受的文本格式。"""
    return "[" + ",".join(f"{value:.9g}" for value in vector) + "]"


def hybrid_search(conn: Connection, data: dict[str, Any]) -> list[dict[str, Any]]:
    brand = get_brand(conn, data["brand_code"])
    query_vector = embed_text(data["query"], input_type="query")
    segmented_query = data.get("segmented_query") or segment_for_search(data["query"])
    scope = data.get("scope", {})
    knowledge_types = data.get("knowledge_types", [])

    # RRF 常数 60 是常见稳健默认值；权威等级越低，权重越高。
    sql = """
    WITH semantic AS MATERIALIZED (
        SELECT
            a.chunk_id,
            row_number() OVER (
                ORDER BY e.embedding <=> %(query_vector)s::halfvec(1536)
            ) AS rank_no
        FROM active_knowledge_chunks a
        JOIN kb_text_embeddings e ON e.chunk_id = a.chunk_id
        JOIN embedding_models m ON m.id = e.model_id AND m.active = true
        WHERE a.brand_id = %(brand_id)s
          AND (%(scope)s::jsonb = '{}'::jsonb OR a.scope @> %(scope)s::jsonb)
          AND (
              cardinality(%(knowledge_types)s::text[]) = 0
              OR a.knowledge_type::text = ANY(%(knowledge_types)s::text[])
          )
        ORDER BY e.embedding <=> %(query_vector)s::halfvec(1536)
        LIMIT %(semantic_candidates)s
    ),
    lexical AS MATERIALIZED (
        SELECT
            a.chunk_id,
            row_number() OVER (
                ORDER BY ts_rank_cd(
                    a.search_vector,
                    plainto_tsquery('simple', %(segmented_query)s)
                ) DESC
            ) AS rank_no
        FROM active_knowledge_chunks a
        WHERE a.brand_id = %(brand_id)s
          AND a.search_vector @@ plainto_tsquery('simple', %(segmented_query)s)
          AND (%(scope)s::jsonb = '{}'::jsonb OR a.scope @> %(scope)s::jsonb)
          AND (
              cardinality(%(knowledge_types)s::text[]) = 0
              OR a.knowledge_type::text = ANY(%(knowledge_types)s::text[])
          )
        ORDER BY ts_rank_cd(
            a.search_vector,
            plainto_tsquery('simple', %(segmented_query)s)
        ) DESC
        LIMIT %(lexical_candidates)s
    ),
    fused AS (
        SELECT
            coalesce(s.chunk_id, l.chunk_id) AS chunk_id,
            coalesce(1.0 / (60 + s.rank_no), 0) +
            coalesce(1.0 / (60 + l.rank_no), 0) AS rrf_score
        FROM semantic s
        FULL OUTER JOIN lexical l ON l.chunk_id = s.chunk_id
    )
    SELECT
        a.chunk_id, a.version_id, a.item_id,
        a.knowledge_type::text, a.canonical_key, a.title,
        a.chunk_type::text, a.text,
        (
            f.rrf_score *
            CASE a.authority_level
                WHEN 1 THEN 1.30 WHEN 2 THEN 1.20 WHEN 3 THEN 1.10
                WHEN 4 THEN 0.90 WHEN 5 THEN 0.75 ELSE 0.0
            END *
            coalesce(0.80 + 0.20 * a.confidence, 0.90)
        )::float8 AS score,
        a.authority_level, a.confidence, a.scope, a.attributes,
        s.title AS source_title,
        sv.version_number AS source_version,
        a.approved_by
    FROM fused f
    JOIN active_knowledge_chunks a ON a.chunk_id = f.chunk_id
    LEFT JOIN kb_item_versions iv ON iv.id = a.version_id
    LEFT JOIN kb_source_versions sv ON sv.id = iv.source_version_id
    LEFT JOIN kb_sources s ON s.id = sv.source_id
    ORDER BY score DESC
    LIMIT %(top_k)s
    """
    params = {
        "query_vector": _vector_literal(query_vector),
        "segmented_query": segmented_query,
        "brand_id": brand["id"],
        "scope": json.dumps(scope, ensure_ascii=False),
        "knowledge_types": knowledge_types,
        "semantic_candidates": data["semantic_candidates"],
        "lexical_candidates": data["lexical_candidates"],
        "top_k": data["top_k"],
    }
    conn.execute("SET LOCAL hnsw.iterative_scan = strict_order")
    conn.execute("SET LOCAL hnsw.ef_search = 100")
    return conn.execute(sql, params).fetchall()
