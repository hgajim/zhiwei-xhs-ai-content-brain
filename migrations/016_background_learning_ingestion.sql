-- 连续导入：把耗时的文章分析和自动吸收交给后台任务。
ALTER TABLE kb_jobs DROP CONSTRAINT IF EXISTS kb_jobs_job_type_check;
ALTER TABLE kb_jobs ADD CONSTRAINT kb_jobs_job_type_check CHECK (job_type IN (
  'embed_chunk', 'activate_version', 'deprecate_old_chunks',
  'embed_asset', 'rebuild_model_embeddings', 'analyze_image', 'embed_image',
  'ingest_learning'
));
