-- 品牌小红书动态知识库：初始数据库结构
-- 注意：生产数据库应使用迁移工具执行，避免直接修改已生效表。

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TYPE source_type AS ENUM (
    'brand_document', 'product_document', 'campaign_brief',
    'creator_submission', 'reviewed_creator_content',
    'competitor_content', 'platform_rule', 'manual_entry'
);

CREATE TYPE knowledge_type AS ENUM (
    'brand_rule', 'product_fact', 'tone_rule', 'visual_rule',
    'review_case', 'review_annotation', 'preference_pair',
    'competitor_pattern', 'experience_hypothesis', 'exception', 'example'
);

CREATE TYPE knowledge_status AS ENUM (
    'candidate', 'reviewed', 'active', 'contested', 'deprecated', 'superseded'
);

CREATE TYPE chunk_type AS ENUM (
    'principle', 'rule', 'reason', 'positive_example', 'negative_example',
    'original_text', 'revised_text', 'review_comment',
    'competitor_pattern', 'visual_description'
);

CREATE TYPE job_status AS ENUM (
    'pending', 'running', 'succeeded', 'failed', 'cancelled'
);

CREATE TYPE edge_type AS ENUM (
    'applies_to', 'violates', 'exemplifies', 'supports', 'contradicts',
    'exception_to', 'supersedes', 'derived_from', 'similar_to',
    'preferred_over', 'transferable_to'
);

CREATE TABLE brands (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    timezone text NOT NULL DEFAULT 'Asia/Shanghai',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE brands IS '品牌或子品牌；所有业务数据必须归属于一个品牌';

CREATE TABLE kb_sources (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id uuid NOT NULL REFERENCES brands(id),
    source_type source_type NOT NULL,
    external_id text,
    title text NOT NULL,
    original_uri text,
    owner text,
    authority_level smallint NOT NULL DEFAULT 5 CHECK (authority_level BETWEEN 1 AND 6),
    metadata jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (brand_id, source_type, external_id)
);

COMMENT ON TABLE kb_sources IS '原始知识来源，例如品牌手册、达人稿、竞品案例';

CREATE TABLE kb_source_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid NOT NULL REFERENCES kb_sources(id),
    version_number integer NOT NULL CHECK (version_number > 0),
    content_hash text NOT NULL,
    raw_text text,
    storage_uri text,
    mime_type text,
    captured_at timestamptz NOT NULL DEFAULT now(),
    valid_from timestamptz,
    valid_to timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_id, version_number),
    UNIQUE (source_id, content_hash)
);

CREATE TABLE kb_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id uuid NOT NULL REFERENCES brands(id),
    knowledge_type knowledge_type NOT NULL,
    canonical_key text NOT NULL,
    title text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (brand_id, canonical_key)
);

COMMENT ON TABLE kb_items IS '稳定知识身份；标题可以变化，canonical_key 不应随版本改变';

CREATE TABLE kb_item_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id uuid NOT NULL REFERENCES kb_items(id),
    source_version_id uuid REFERENCES kb_source_versions(id),
    version_number integer NOT NULL CHECK (version_number > 0),
    status knowledge_status NOT NULL DEFAULT 'candidate',
    summary text NOT NULL,
    content text NOT NULL,
    authority_level smallint NOT NULL CHECK (authority_level BETWEEN 1 AND 6),
    confidence numeric(4,3) CHECK (confidence BETWEEN 0 AND 1),
    scope jsonb NOT NULL DEFAULT '{}',
    attributes jsonb NOT NULL DEFAULT '{}',
    valid_from timestamptz,
    valid_to timestamptz,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    supersedes_version_id uuid REFERENCES kb_item_versions(id),
    approved_by text,
    approved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (item_id, version_number)
);

CREATE INDEX idx_kb_item_versions_item ON kb_item_versions(item_id);
CREATE INDEX idx_kb_item_versions_status ON kb_item_versions(status);
CREATE INDEX idx_kb_item_versions_scope ON kb_item_versions USING gin(scope jsonb_path_ops);
CREATE INDEX idx_kb_item_versions_attributes ON kb_item_versions USING gin(attributes jsonb_path_ops);

CREATE TABLE kb_chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id uuid NOT NULL REFERENCES brands(id),
    item_version_id uuid NOT NULL REFERENCES kb_item_versions(id),
    chunk_type chunk_type NOT NULL,
    ordinal integer NOT NULL DEFAULT 0,
    text text NOT NULL CHECK (length(btrim(text)) > 0),
    search_terms text NOT NULL DEFAULT '',
    content_hash text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}',
    active boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('simple', coalesce(text, '') || ' ' || coalesce(search_terms, ''))
    ) STORED,
    UNIQUE (item_version_id, ordinal, content_hash)
);

CREATE INDEX idx_kb_chunks_brand_active ON kb_chunks(brand_id, active);
CREATE INDEX idx_kb_chunks_search ON kb_chunks USING gin(search_vector);
CREATE INDEX idx_kb_chunks_trgm ON kb_chunks USING gin(text gin_trgm_ops);

CREATE TABLE embedding_models (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    model_key text NOT NULL UNIQUE,
    provider text NOT NULL,
    model_name text NOT NULL,
    modality text NOT NULL CHECK (modality IN ('text', 'image', 'multimodal')),
    dimensions integer NOT NULL CHECK (dimensions > 0),
    normalized boolean NOT NULL DEFAULT true,
    active boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_one_active_embedding_model_per_modality
ON embedding_models(modality)
WHERE active = true;

-- 第一版文本索引固定为 1536 维。更换维度必须建立新表或执行迁移。
CREATE TABLE kb_text_embeddings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id uuid NOT NULL REFERENCES brands(id),
    chunk_id uuid NOT NULL REFERENCES kb_chunks(id) ON DELETE CASCADE,
    model_id uuid NOT NULL REFERENCES embedding_models(id),
    embedding halfvec(1536) NOT NULL,
    input_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (chunk_id, model_id, input_hash)
);

CREATE INDEX idx_kb_text_embeddings_model ON kb_text_embeddings(model_id);
CREATE INDEX idx_kb_text_embeddings_hnsw
ON kb_text_embeddings USING hnsw (embedding halfvec_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE TABLE kb_assets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id uuid NOT NULL REFERENCES brands(id),
    source_version_id uuid REFERENCES kb_source_versions(id),
    asset_type text NOT NULL CHECK (asset_type IN ('image', 'video', 'keyframe', 'document_page')),
    storage_uri text NOT NULL,
    content_hash text NOT NULL,
    mime_type text,
    width integer,
    height integer,
    duration_ms integer,
    ocr_text text,
    transcript text,
    machine_description text,
    metadata jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (brand_id, content_hash)
);

CREATE TABLE kb_asset_annotations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id uuid NOT NULL REFERENCES kb_assets(id) ON DELETE CASCADE,
    item_version_id uuid REFERENCES kb_item_versions(id),
    region jsonb NOT NULL DEFAULT '{}',
    dimension text NOT NULL,
    observation text NOT NULL,
    impact text,
    correction_direction text,
    reviewer text,
    confidence numeric(4,3) CHECK (confidence BETWEEN 0 AND 1),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE review_cases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id uuid NOT NULL REFERENCES brands(id),
    source_id uuid REFERENCES kb_sources(id),
    product_code text,
    creator_id text,
    creator_type text,
    content_type text,
    campaign_code text,
    overall_decision text,
    reviewer text,
    reviewed_at timestamptz,
    context jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE review_content_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    review_case_id uuid NOT NULL REFERENCES review_cases(id) ON DELETE CASCADE,
    version_number integer NOT NULL CHECK (version_number > 0),
    version_type text NOT NULL CHECK (version_type IN (
        'creator_original', 'reviewer_revision', 'creator_revision',
        'approved_final', 'published'
    )),
    title text,
    body text,
    assets jsonb NOT NULL DEFAULT '[]',
    content_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (review_case_id, version_number)
);

CREATE TABLE review_annotations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    review_case_id uuid NOT NULL REFERENCES review_cases(id) ON DELETE CASCADE,
    content_version_id uuid NOT NULL REFERENCES review_content_versions(id) ON DELETE CASCADE,
    location_type text NOT NULL CHECK (location_type IN ('title', 'body_span', 'image_region', 'video_segment', 'overall')),
    location_data jsonb NOT NULL DEFAULT '{}',
    original_text text,
    revised_text text,
    decision text NOT NULL CHECK (decision IN ('keep', 'rewrite', 'delete', 'reject', 'review')),
    reason text NOT NULL,
    reason_codes text[] NOT NULL DEFAULT '{}',
    severity text CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    reviewer_confidence numeric(4,3) CHECK (reviewer_confidence BETWEEN 0 AND 1),
    linked_rule_version_id uuid REFERENCES kb_item_versions(id),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE preference_pairs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id uuid NOT NULL REFERENCES brands(id),
    context jsonb NOT NULL,
    option_a jsonb NOT NULL,
    option_b jsonb NOT NULL,
    preferred_option char(1) CHECK (preferred_option IN ('A', 'B', 'T')),
    preference_strength smallint CHECK (preference_strength BETWEEN 1 AND 3),
    reasons text[] NOT NULL DEFAULT '{}',
    explanation text,
    reviewer text,
    reviewer_confidence numeric(4,3) CHECK (reviewer_confidence BETWEEN 0 AND 1),
    status knowledge_status NOT NULL DEFAULT 'candidate',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE kb_edges (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id uuid NOT NULL REFERENCES brands(id),
    from_item_id uuid NOT NULL REFERENCES kb_items(id),
    to_item_id uuid NOT NULL REFERENCES kb_items(id),
    edge_type edge_type NOT NULL,
    weight numeric(4,3) NOT NULL DEFAULT 1.0 CHECK (weight BETWEEN 0 AND 1),
    evidence jsonb NOT NULL DEFAULT '{}',
    status knowledge_status NOT NULL DEFAULT 'candidate',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (from_item_id, to_item_id, edge_type)
);

CREATE TABLE kb_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id uuid NOT NULL REFERENCES brands(id),
    job_type text NOT NULL CHECK (job_type IN (
        'embed_chunk', 'activate_version', 'deprecate_old_chunks',
        'embed_asset', 'rebuild_model_embeddings'
    )),
    entity_type text NOT NULL,
    entity_id uuid NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}',
    status job_status NOT NULL DEFAULT 'pending',
    attempts integer NOT NULL DEFAULT 0,
    max_attempts integer NOT NULL DEFAULT 5,
    available_at timestamptz NOT NULL DEFAULT now(),
    locked_at timestamptz,
    locked_by text,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_kb_jobs_pending ON kb_jobs(status, available_at)
WHERE status = 'pending';

-- 工作流查询时只使用这个视图，避免误读候选或过期知识。
CREATE VIEW active_knowledge_chunks AS
SELECT
    c.id AS chunk_id,
    c.brand_id,
    c.chunk_type,
    c.text,
    c.search_terms,
    c.search_vector,
    c.metadata AS chunk_metadata,
    v.id AS version_id,
    v.summary,
    v.authority_level,
    v.confidence,
    v.scope,
    v.attributes,
    v.valid_from,
    v.approved_by,
    v.approved_at,
    i.id AS item_id,
    i.knowledge_type,
    i.canonical_key,
    i.title
FROM kb_chunks c
JOIN kb_item_versions v ON v.id = c.item_version_id
JOIN kb_items i ON i.id = v.item_id
WHERE c.active = true
  AND v.status = 'active'
  AND (v.valid_from IS NULL OR v.valid_from <= now())
  AND (v.valid_to IS NULL OR v.valid_to > now());
