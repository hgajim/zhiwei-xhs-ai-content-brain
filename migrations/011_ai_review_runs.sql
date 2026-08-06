CREATE TABLE xhs_ai_review_runs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), brand_id uuid NOT NULL REFERENCES brands(id),
 created_by text, title text NOT NULL DEFAULT '', original_text text NOT NULL,
 revised_text text, score integer CHECK(score BETWEEN 0 AND 100),
 decision text CHECK(decision IN ('pass','minor_revision','major_revision','reject')),
 summary text, issues jsonb NOT NULL DEFAULT '[]', cited_knowledge_ids uuid[] NOT NULL DEFAULT '{}',
 model_name text, status text NOT NULL DEFAULT 'processing' CHECK(status IN ('processing','completed','failed')),
 error_message text, absorbed_session_id uuid REFERENCES xhs_learning_sessions(id),
 created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz
);
CREATE INDEX idx_xhs_ai_review_runs_brand ON xhs_ai_review_runs(brand_id,created_at DESC);
GRANT SELECT,INSERT,UPDATE,DELETE ON xhs_ai_review_runs TO brand_kb;
