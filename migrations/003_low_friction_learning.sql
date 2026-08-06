-- 低操作成本教学层
-- 用户只需上传素材并给出一句整体说明；AI负责拆解成细粒度候选经验。

CREATE TABLE xhs_learning_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id uuid NOT NULL REFERENCES brands(id),
    learning_mode text NOT NULL CHECK (learning_mode IN (
        'positive_example', 'negative_example', 'revision_pair', 'experience'
    )),
    original_article_version_id uuid REFERENCES xhs_article_versions(id),
    revised_article_version_id uuid REFERENCES xhs_article_versions(id),
    user_feedback text,
    status text NOT NULL DEFAULT 'processing' CHECK (status IN (
        'processing', 'ready', 'needs_confirmation', 'confirmed', 'failed'
    )),
    analysis_summary text,
    model_name text,
    prompt_version text NOT NULL DEFAULT 'low-friction-v1',
    raw_analysis jsonb NOT NULL DEFAULT '{}',
    error_message text,
    created_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    confirmed_at timestamptz
);

CREATE INDEX idx_xhs_learning_sessions_brand
ON xhs_learning_sessions(brand_id, created_at DESC);

COMMENT ON TABLE xhs_learning_sessions IS '一次低操作教学会话：正例、反例、前后稿或纯经验';
COMMENT ON COLUMN xhs_learning_sessions.user_feedback IS '用户可选的一句话评价，不要求逐项标注';

CREATE TABLE xhs_learning_insights (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL REFERENCES xhs_learning_sessions(id) ON DELETE CASCADE,
    ordinal integer NOT NULL,
    dimension text NOT NULL CHECK (dimension IN (
        'title', 'opening', 'body', 'closing', 'hashtag', 'tone', 'structure',
        'selling_point', 'compliance', 'creator_fit', 'visual', 'overall', 'other'
    )),
    sentiment text NOT NULL CHECK (sentiment IN ('positive', 'negative', 'revision', 'neutral')),
    location_data jsonb NOT NULL DEFAULT '{}',
    evidence_before text,
    evidence_after text,
    judgment text NOT NULL,
    rationale text NOT NULL,
    reusable_rule text NOT NULL,
    applicability jsonb NOT NULL DEFAULT '{}',
    exceptions jsonb NOT NULL DEFAULT '{}',
    reason_codes text[] NOT NULL DEFAULT '{}',
    severity text CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    confidence numeric(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    needs_confirmation boolean NOT NULL DEFAULT true,
    confirmation_reason text,
    status text NOT NULL DEFAULT 'candidate' CHECK (status IN (
        'candidate', 'accepted', 'rejected', 'edited'
    )),
    user_correction text,
    knowledge_version_id uuid REFERENCES kb_item_versions(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(session_id, ordinal)
);

CREATE INDEX idx_xhs_learning_insights_review_queue
ON xhs_learning_insights(session_id, needs_confirmation, status);

COMMENT ON TABLE xhs_learning_insights IS 'AI从一次教学输入中自动拆出的候选经验；默认不直接污染正式知识';
COMMENT ON COLUMN xhs_learning_insights.needs_confirmation IS '低置信度、与用户描述不一致或高风险结论才要求重点确认';
