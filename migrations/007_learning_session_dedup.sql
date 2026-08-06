-- 学习会话幂等保护：同一品牌、同一教学类型、相同正文和相同评价只吸收一次。
-- 历史重复记录不删除；每组仅选择一条（优先已确认）作为后续重复请求的复用对象。
ALTER TABLE xhs_learning_sessions ADD COLUMN IF NOT EXISTS input_hash text;

WITH ranked AS (
    SELECT s.id,
        encode(digest(concat_ws('|', s.learning_mode,
            coalesce(ov.content_hash, ''), coalesce(rv.content_hash, ''),
            regexp_replace(btrim(coalesce(s.user_feedback, '')), '\s+', ' ', 'g')
        ), 'sha256'), 'hex') AS calculated_hash,
        row_number() OVER (
            PARTITION BY s.brand_id, concat_ws('|', s.learning_mode,
                coalesce(ov.content_hash, ''), coalesce(rv.content_hash, ''),
                regexp_replace(btrim(coalesce(s.user_feedback, '')), '\s+', ' ', 'g'))
            ORDER BY CASE s.status WHEN 'confirmed' THEN 0 WHEN 'ready' THEN 1
                WHEN 'needs_confirmation' THEN 2 WHEN 'processing' THEN 3 ELSE 4 END,
                s.created_at ASC
        ) AS duplicate_rank
    FROM xhs_learning_sessions s
    LEFT JOIN xhs_article_versions ov ON ov.id = s.original_article_version_id
    LEFT JOIN xhs_article_versions rv ON rv.id = s.revised_article_version_id
)
UPDATE xhs_learning_sessions target
SET input_hash = ranked.calculated_hash
FROM ranked
WHERE target.id = ranked.id AND ranked.duplicate_rank = 1 AND target.input_hash IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_xhs_learning_sessions_brand_input_hash
ON xhs_learning_sessions(brand_id, input_hash) WHERE input_hash IS NOT NULL;

COMMENT ON COLUMN xhs_learning_sessions.input_hash IS
'输入内容稳定指纹，用于防止同一材料、教学类型和用户评价被重复分析与吸收';
