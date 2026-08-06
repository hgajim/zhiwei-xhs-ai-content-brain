-- 图片理解与多模态向量层。
ALTER TABLE kb_jobs DROP CONSTRAINT IF EXISTS kb_jobs_job_type_check;
ALTER TABLE kb_jobs ADD CONSTRAINT kb_jobs_job_type_check CHECK (job_type IN (
    'embed_chunk', 'activate_version', 'deprecate_old_chunks', 'embed_asset',
    'rebuild_model_embeddings', 'analyze_image', 'embed_image'
));

CREATE TABLE IF NOT EXISTS xhs_image_analyses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), brand_id uuid NOT NULL REFERENCES brands(id),
    asset_id uuid NOT NULL REFERENCES kb_assets(id) ON DELETE CASCADE,
    article_version_id uuid NOT NULL REFERENCES xhs_article_versions(id) ON DELETE CASCADE,
    ordinal integer NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'processing' CHECK (status IN ('processing','succeeded','failed')),
    model_name text, prompt_version text NOT NULL DEFAULT 'xhs-image-understanding-v1',
    asset_role text, visual_type text, summary text, ocr_text text,
    objects jsonb NOT NULL DEFAULT '[]', product_exposure jsonb NOT NULL DEFAULT '{}',
    aesthetic jsonb NOT NULL DEFAULT '{}', content_functions jsonb NOT NULL DEFAULT '[]',
    brand_fit_score numeric(5,2), cover_click_score numeric(5,2), selling_power_score numeric(5,2),
    compliance_risks jsonb NOT NULL DEFAULT '[]', evidence jsonb NOT NULL DEFAULT '[]',
    reusable_visual_rules jsonb NOT NULL DEFAULT '[]', confidence numeric(5,2),
    raw_analysis jsonb NOT NULL DEFAULT '{}', error_message text,
    created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
    UNIQUE(asset_id, article_version_id, prompt_version)
);
CREATE INDEX IF NOT EXISTS idx_xhs_image_analyses_version ON xhs_image_analyses(article_version_id, ordinal);

CREATE TABLE IF NOT EXISTS kb_multimodal_embeddings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), brand_id uuid NOT NULL REFERENCES brands(id),
    article_version_id uuid REFERENCES xhs_article_versions(id) ON DELETE CASCADE,
    asset_id uuid REFERENCES kb_assets(id) ON DELETE CASCADE,
    analysis_id uuid REFERENCES xhs_image_analyses(id) ON DELETE CASCADE,
    modality text NOT NULL CHECK (modality IN ('image','image_text_fusion')),
    representation_type text NOT NULL CHECK (representation_type IN ('independent','fused')),
    model_name text NOT NULL, dimensions integer NOT NULL DEFAULT 1536,
    embedding halfvec(1536) NOT NULL, input_hash text NOT NULL,
    active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(asset_id, article_version_id, modality, model_name, input_hash)
);
CREATE INDEX IF NOT EXISTS idx_kb_multimodal_embedding_brand ON kb_multimodal_embeddings(brand_id, modality);
CREATE INDEX IF NOT EXISTS idx_kb_multimodal_embedding_hnsw ON kb_multimodal_embeddings USING hnsw (embedding halfvec_cosine_ops) WITH (m=16, ef_construction=64);
GRANT SELECT, INSERT, UPDATE, DELETE ON xhs_image_analyses TO brand_kb;
GRANT SELECT, INSERT, UPDATE, DELETE ON kb_multimodal_embeddings TO brand_kb;
