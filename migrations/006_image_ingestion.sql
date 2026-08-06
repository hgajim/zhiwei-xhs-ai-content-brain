-- 图片摄入层：图片文件保存在对象目录，数据库保存元数据及文章版本关联。
CREATE TABLE IF NOT EXISTS xhs_article_assets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    article_version_id uuid NOT NULL REFERENCES xhs_article_versions(id) ON DELETE CASCADE,
    asset_id uuid REFERENCES kb_assets(id) ON DELETE SET NULL,
    ordinal integer NOT NULL CHECK (ordinal >= 0),
    source_url text NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'stored', 'failed'
    )),
    error_message text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (article_version_id, ordinal)
);

CREATE INDEX IF NOT EXISTS idx_xhs_article_assets_version
ON xhs_article_assets(article_version_id, status, ordinal);

CREATE INDEX IF NOT EXISTS idx_xhs_article_assets_asset
ON xhs_article_assets(asset_id)
WHERE asset_id IS NOT NULL;

COMMENT ON TABLE xhs_article_assets IS '文章版本与本地持久化图片资产的关联；单图失败不影响正文摄入';
COMMENT ON COLUMN xhs_article_assets.source_url IS '抓取时使用的原始图片地址，仅作来源追溯';
