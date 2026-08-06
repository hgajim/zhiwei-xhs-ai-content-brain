-- 保留原始文章，允许撤销其派生知识并在之后重新学习。
ALTER TABLE xhs_learning_sessions
    ADD COLUMN IF NOT EXISTS forgotten_at timestamptz,
    ADD COLUMN IF NOT EXISTS forgotten_by text;

ALTER TABLE xhs_learning_sessions DROP CONSTRAINT IF EXISTS xhs_learning_sessions_status_check;
ALTER TABLE xhs_learning_sessions ADD CONSTRAINT xhs_learning_sessions_status_check
CHECK (status IN ('processing', 'ready', 'needs_confirmation', 'confirmed', 'failed', 'forgotten'));

CREATE TABLE IF NOT EXISTS xhs_article_forget_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id uuid NOT NULL REFERENCES xhs_articles(id) ON DELETE CASCADE,
    brand_id uuid NOT NULL REFERENCES brands(id),
    forgotten_by text NOT NULL,
    reason text,
    affected_session_ids uuid[] NOT NULL DEFAULT '{}',
    affected_knowledge_version_ids uuid[] NOT NULL DEFAULT '{}',
    deletion_summary jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_xhs_article_forget_events_article
ON xhs_article_forget_events(article_id, created_at DESC);

COMMENT ON TABLE xhs_article_forget_events IS '文章保留、派生知识被遗忘时的不可变审计记录';

GRANT SELECT, INSERT ON xhs_article_forget_events TO brand_kb;
