-- 小红书文章摄入层
-- 目标：保存达人稿件的完整版本链、结构片段、审核批注、批量导入状态，
-- 并将已确认的文章或审核经验沉淀到现有动态知识库。

ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'xiaohongshu_article';

ALTER TYPE chunk_type ADD VALUE IF NOT EXISTS 'article_full';
ALTER TYPE chunk_type ADD VALUE IF NOT EXISTS 'article_title';
ALTER TYPE chunk_type ADD VALUE IF NOT EXISTS 'article_opening';
ALTER TYPE chunk_type ADD VALUE IF NOT EXISTS 'article_body';
ALTER TYPE chunk_type ADD VALUE IF NOT EXISTS 'article_closing';
ALTER TYPE chunk_type ADD VALUE IF NOT EXISTS 'article_hashtags';
ALTER TYPE chunk_type ADD VALUE IF NOT EXISTS 'review_original';
ALTER TYPE chunk_type ADD VALUE IF NOT EXISTS 'review_revision';

CREATE TABLE xhs_articles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id uuid NOT NULL REFERENCES brands(id),
    source_id uuid NOT NULL REFERENCES kb_sources(id),

    article_type text NOT NULL CHECK (article_type IN (
        'creator_submission',
        'approved_creator_content',
        'published_creator_content',
        'competitor_content',
        'brand_owned_content'
    )),

    platform_note_id text,
    external_id text,
    creator_id text,
    creator_name text,
    creator_type text,
    product_code text,
    campaign_code text,
    content_type text,
    source_url text,
    published_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    UNIQUE (brand_id, external_id)
);

CREATE UNIQUE INDEX idx_xhs_articles_platform_note
ON xhs_articles(brand_id, platform_note_id)
WHERE platform_note_id IS NOT NULL;

CREATE INDEX idx_xhs_articles_context
ON xhs_articles(brand_id, product_code, creator_type, content_type);

COMMENT ON TABLE xhs_articles IS '小红书文章稳定身份；达人多轮稿件共用同一个文章ID';
COMMENT ON COLUMN xhs_articles.article_type IS '达人投稿、已批准文章、已发布文章、竞品文章或品牌自有文章';

CREATE TABLE xhs_article_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id uuid NOT NULL REFERENCES xhs_articles(id) ON DELETE CASCADE,
    source_version_id uuid NOT NULL REFERENCES kb_source_versions(id),
    version_number integer NOT NULL CHECK (version_number > 0),
    version_type text NOT NULL CHECK (version_type IN (
        'creator_original',
        'reviewer_revision',
        'creator_revision',
        'approved_final',
        'published'
    )),
    title text NOT NULL DEFAULT '',
    body text NOT NULL DEFAULT '',
    hashtags text[] NOT NULL DEFAULT '{}',
    mentioned_products text[] NOT NULL DEFAULT '{}',
    normalized_text text NOT NULL,
    content_hash text NOT NULL,
    status text NOT NULL DEFAULT 'uploaded' CHECK (status IN (
        'uploaded', 'parsed', 'reviewed', 'approved', 'active', 'rejected', 'failed'
    )),
    knowledge_version_id uuid REFERENCES kb_item_versions(id),
    metadata jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (article_id, version_number),
    UNIQUE (article_id, content_hash)
);

CREATE INDEX idx_xhs_article_versions_article
ON xhs_article_versions(article_id, version_number DESC);

COMMENT ON TABLE xhs_article_versions IS '达人原稿、品牌修改稿、达人修改稿、批准终稿和发布稿的完整版本链';

CREATE TABLE xhs_article_chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id uuid NOT NULL REFERENCES brands(id),
    article_version_id uuid NOT NULL REFERENCES xhs_article_versions(id) ON DELETE CASCADE,
    chunk_type chunk_type NOT NULL,
    ordinal integer NOT NULL,
    original_text text NOT NULL CHECK (length(btrim(original_text)) > 0),
    embedding_text text NOT NULL CHECK (length(btrim(embedding_text)) > 0),
    search_terms text NOT NULL DEFAULT '',
    content_hash text NOT NULL,
    active boolean NOT NULL DEFAULT false,
    kb_chunk_id uuid REFERENCES kb_chunks(id),
    metadata jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (article_version_id, ordinal, content_hash)
);

CREATE INDEX idx_xhs_article_chunks_version
ON xhs_article_chunks(article_version_id, ordinal);

CREATE INDEX idx_xhs_article_chunks_active
ON xhs_article_chunks(brand_id, active);

COMMENT ON TABLE xhs_article_chunks IS '按标题、开头、正文、结尾和话题拆分的小红书文章片段';
COMMENT ON COLUMN xhs_article_chunks.original_text IS '达人真实原文，永不被上下文增强文本替代';
COMMENT ON COLUMN xhs_article_chunks.embedding_text IS '加入产品、达人和内容类型上下文后送入Embedding模型的文本';

CREATE TABLE xhs_ingestion_batches (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id uuid NOT NULL REFERENCES brands(id),
    batch_name text,
    status text NOT NULL DEFAULT 'running' CHECK (status IN (
        'running', 'succeeded', 'partial_success', 'failed'
    )),
    total_count integer NOT NULL DEFAULT 0,
    inserted_count integer NOT NULL DEFAULT 0,
    deduplicated_count integer NOT NULL DEFAULT 0,
    failed_count integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE xhs_ingestion_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id uuid NOT NULL REFERENCES xhs_ingestion_batches(id) ON DELETE CASCADE,
    input_index integer NOT NULL,
    external_id text,
    status text NOT NULL CHECK (status IN ('inserted', 'deduplicated', 'failed')),
    article_id uuid REFERENCES xhs_articles(id),
    article_version_id uuid REFERENCES xhs_article_versions(id),
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (batch_id, input_index)
);

ALTER TABLE review_cases
ADD COLUMN IF NOT EXISTS article_version_id uuid REFERENCES xhs_article_versions(id);

ALTER TABLE review_annotations
ADD COLUMN IF NOT EXISTS distilled_knowledge_version_id uuid REFERENCES kb_item_versions(id);

CREATE INDEX idx_review_cases_article_version
ON review_cases(article_version_id);

