-- 小红书内容运营类型标签：由摄入分析生成，确认前也可审阅和重新计算。
CREATE TABLE IF NOT EXISTS xhs_content_type_labels (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL REFERENCES xhs_learning_sessions(id) ON DELETE CASCADE,
    article_version_id uuid REFERENCES xhs_article_versions(id) ON DELETE CASCADE,
    label_role text NOT NULL DEFAULT 'learning_target' CHECK (label_role IN ('learning_target', 'original', 'revised')),
    primary_type text NOT NULL CHECK (primary_type IN (
        '大曝光笔记', '强种草笔记', '搜索承接笔记', '信任背书笔记',
        '场景心智笔记', '产品认知笔记', '对比决策笔记', '口碑扩散笔记',
        '活动转化笔记', '品牌价值笔记', '互动讨论笔记', '低效宣传笔记'
    )),
    secondary_types jsonb NOT NULL DEFAULT '[]',
    target_audience jsonb NOT NULL DEFAULT '[]',
    user_stage text,
    expected_user_change text,
    confidence numeric(5,2) NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    objective_score numeric(5,2) CHECK (objective_score BETWEEN 0 AND 100),
    rationale text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '[]',
    content_mechanism jsonb NOT NULL DEFAULT '{}',
    missing_information jsonb NOT NULL DEFAULT '[]',
    prompt_version text NOT NULL DEFAULT 'content-type-crispe-v1',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(session_id, article_version_id, label_role)
);

CREATE INDEX IF NOT EXISTS idx_xhs_content_type_labels_primary
ON xhs_content_type_labels(primary_type, confidence DESC);

CREATE INDEX IF NOT EXISTS idx_xhs_content_type_labels_article
ON xhs_content_type_labels(article_version_id);

COMMENT ON TABLE xhs_content_type_labels IS '摄入阶段生成的内容运营类型标签；主类型唯一，辅助类型最多两个';
GRANT SELECT, INSERT, UPDATE, DELETE ON xhs_content_type_labels TO brand_kb;
