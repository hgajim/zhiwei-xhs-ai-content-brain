-- 第一阶段：吸收质量健康度快照，为后续趋势、检索质量和实战评估保留版本化数据。
CREATE TABLE IF NOT EXISTS xhs_absorption_health_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id uuid NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
  formula_version text NOT NULL,
  overall_score numeric(5,2) NOT NULL CHECK (overall_score BETWEEN 0 AND 100),
  material_quality_score numeric(5,2) NOT NULL,
  signal_balance_score numeric(5,2) NOT NULL,
  coverage_score numeric(5,2) NOT NULL,
  purity_score numeric(5,2) NOT NULL,
  mode_metrics jsonb NOT NULL DEFAULT '{}',
  content_type_distribution jsonb NOT NULL DEFAULT '{}',
  quality_metrics jsonb NOT NULL DEFAULT '{}',
  recommendations jsonb NOT NULL DEFAULT '[]',
  captured_bucket timestamptz NOT NULL DEFAULT date_trunc('hour', now()),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(brand_id, formula_version, captured_bucket)
);

CREATE INDEX IF NOT EXISTS idx_absorption_health_brand_time
ON xhs_absorption_health_snapshots(brand_id, created_at DESC);

GRANT SELECT,INSERT,UPDATE,DELETE ON xhs_absorption_health_snapshots TO brand_kb;

COMMENT ON TABLE xhs_absorption_health_snapshots IS '吸收质量健康度快照；第一阶段为数据健康，后续叠加检索与实战效果';

