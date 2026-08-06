-- 品牌级大语言模型设置
-- API Key只保存密文；前端查询接口永远不返回明文。

CREATE TABLE brand_ai_settings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id uuid NOT NULL REFERENCES brands(id),
    purpose text NOT NULL DEFAULT 'content_learning' CHECK (purpose IN (
        'content_learning', 'content_review', 'knowledge_governance'
    )),
    provider text NOT NULL DEFAULT 'openai_compatible',
    base_url text NOT NULL,
    model_name text NOT NULL,
    api_key_encrypted text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    extra_options jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(brand_id, purpose)
);

COMMENT ON TABLE brand_ai_settings IS '可由未来前端维护的品牌级大模型配置';
COMMENT ON COLUMN brand_ai_settings.api_key_encrypted IS '使用服务器主密钥加密，禁止返回给前端或写入日志';
