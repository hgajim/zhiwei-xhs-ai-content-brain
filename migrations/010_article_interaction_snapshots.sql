CREATE TABLE xhs_article_interaction_snapshots (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), article_id uuid NOT NULL REFERENCES xhs_articles(id) ON DELETE CASCADE,
 like_count bigint, collect_count bigint, comment_count bigint, share_count bigint,
 captured_at timestamptz NOT NULL DEFAULT now(), source text NOT NULL DEFAULT 'url_import'
);
CREATE INDEX idx_xhs_interactions_article_time ON xhs_article_interaction_snapshots(article_id,captured_at DESC);
GRANT SELECT,INSERT,UPDATE,DELETE ON xhs_article_interaction_snapshots TO brand_kb;
