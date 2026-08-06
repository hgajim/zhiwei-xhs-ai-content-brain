-- A/B审核需要记录本次审核是否调用了个人向量知识库。
ALTER TABLE xhs_ai_review_runs
  ADD COLUMN IF NOT EXISTS knowledge_mode text NOT NULL DEFAULT 'with_knowledge'
  CHECK (knowledge_mode IN ('with_knowledge','without_knowledge'));

