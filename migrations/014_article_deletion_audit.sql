-- 文章永久删除审计：不使用文章外键，确保原文删除后仍能追溯操作。
CREATE TABLE IF NOT EXISTS xhs_article_deletion_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id uuid NOT NULL,
    brand_id uuid NOT NULL REFERENCES brands(id),
    article_title text,
    deleted_by text NOT NULL,
    reason text,
    deletion_summary jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_xhs_article_deletion_events_brand
ON xhs_article_deletion_events(brand_id, created_at DESC);
GRANT SELECT, INSERT ON xhs_article_deletion_events TO brand_kb;
