# AI 项目接续说明（必须先完整阅读）

你正在继续开发“品牌小红书达人广告内容动态知识库”。不要重新从零设计，也不要覆盖已经完成的数据模型。先阅读本文件、`README.md`、`migrations/`及相关服务代码，再检查实际数据库状态。

## 一、用户的真实业务目标

用户是某品牌的小红书运营经理，每天审核合作达人撰写的品牌广告内容。审核依据主要来自：

1. 品牌和产品的明确规范；
2. 品牌审美与语言调性；
3. 同行竞品的优秀文章和可迁移内容方法；
4. 用户本人长期积累但尚未完全结构化的审核经验；
5. 历史达人原稿、修改稿、终稿及逐处审核理由。

最终目标是让 AI 逐步替代人工完成达人稿审核。当前已经从纯后端阶段进入本地前端验证阶段：第一版网页位于`frontend/`，应继续连接现有知识库能力，不要删除或重做已经确认的设计系统。完整审核Agent仍未完成，不能把静态审核示例误报为真实自动审核能力。

最新且最高优先级的产品原则是“降低喂养成本”：用户不应分别说明标题、正文、图片和结构好坏。用户只上传一篇文章、前后稿，或口述一句经验，再可选说一句整体评价；AI负责主动拆解证据、原因、适用条件和候选规则。只有低置信度、高风险或可能冲突的结论才重点要求用户确认。

## 二、核心设计原则

- 原始来源、知识条目、知识版本、检索片段必须分层。
- AI 自动抽取先进入候选区，未经人工确认不能进入生产检索；允许一次整批确认后自动完成知识审批和向量排队，不能强迫用户逐条点击两次。
- 更新知识时创建新版本，旧版本标记为 `superseded`，不能直接覆盖或删除。
- 向量只是可重建索引；原始材料、审核决定和版本记录才是事实源。
- 正式品牌规则、人工审核经验、竞品方法必须使用不同知识类型和权威等级。
- 竞品文章只能成为 `competitor_reference`，不能自动变成本品牌正例或正式规则。
- 有修改意见的达人原稿不能直接批准为正例；正例必须是批准终稿、发布稿，或存在明确审核通过记录。
- 尽量使用中文注释、中文错误信息和中文说明；数据库表名、字段名和API路径保留规范英文。

## 三、当前技术栈

- PostgreSQL 18
- pgvector
- Python 3.12
- FastAPI
- psycopg 3
- 阿里云百炼 `qwen3.7-text-embedding`
- DashScope 北京地域原生接口
- 文本向量维度：1,536
- PostgreSQL向量类型：`halfvec(1536)`
- 距离函数：余弦距离
- 向量索引：HNSW
- 检索方式：百炼稠密向量＋PostgreSQL中文关键词＋RRF融合排序
- 教学理解模型：默认百炼 `qwen-plus`，通过 OpenAI 兼容接口调用
- 大模型配置：支持品牌级、用途级配置，未来前端可选择兼容地址、模型名和API Key

真实密钥和数据库连接只存在本地 `.env` 或数据库加密字段中，相关本地文件已被 `.gitignore` 排除。绝对不要把密钥复制到代码、文档、日志、测试输出或聊天回复中。品牌级API Key使用Fernet加密，读取接口只返回掩码。本地开发自动生成`.local_encryption_key`；网页部署必须显式配置稳定的`APP_ENCRYPTION_KEY`。

## 四、Embedding行为

- 知识片段入库使用 `text_type=document`。
- 工作流查询使用 `text_type=query`。
- 查询使用针对“小红书品牌广告审核知识检索”的英文任务指令。
- 开发伪向量已经关闭。
- 旧测试模型记录保留但已停用；当前活跃模型键为：
  `dashscope:qwen3.7-text-embedding:1536:document-v1`。

## 五、已经完成的数据库能力

### 基础知识库：`migrations/001_init.sql`

- 品牌
- 原始来源及来源版本
- 知识条目及知识版本
- 知识片段
- Embedding模型版本
- 文本向量与HNSW索引
- 图片/视频资产预留表
- 审核案例、内容版本和局部批注
- 偏好对
- 知识关系
- 后台任务队列
- 只返回当前有效知识的视图

### 小红书文章摄入层：`migrations/002_xhs_article_ingestion.sql`

- `xhs_articles`：一篇文章的稳定身份
- `xhs_article_versions`：达人原稿、品牌修改稿、达人修改稿、批准终稿、发布稿
- `xhs_article_chunks`：文章整体、标题、开头、正文、结尾、话题片段
- `xhs_ingestion_batches`：批量导入总状态
- `xhs_ingestion_items`：每篇导入结果和错误隔离
- 审核案例与文章版本关联
- 审核批注与蒸馏候选知识关联

### 低操作教学与模型配置：`003`—`005`

- `xhs_learning_sessions`：一次正例、反例、前后稿或纯经验教学会话
- `xhs_learning_insights`：AI自动拆解出的证据、判断、原因、规则、适用条件、例外和置信度
- `brand_ai_settings`：品牌级、用途级模型地址、模型名和加密API Key
- 前后稿先用确定性差异算法压缩，再交给大模型归因
- `needs_confirmation`只突出低置信度、高风险和推断性结论
- 整批确认支持“默认全接受，只提交少数拒绝或改正项”

五份迁移已经在本机真实 PostgreSQL 数据库执行成功。

## 六、已经完成的后端接口

### 基础知识

- `POST /v1/brands`
- `POST /v1/sources`
- `POST /v1/knowledge`
- `POST /v1/knowledge/{version_id}/approve`
- `POST /v1/search`

### 小红书文章摄入层

- `POST /v1/xhs/articles`：导入单篇文章或新增稿件版本
- `POST /v1/xhs/articles/batch`：最多500篇批量导入，单篇失败不回滚全批
- `GET /v1/xhs/articles/{article_id}`：查看文章及完整版本链
- `GET /v1/xhs/articles?brand_code=demo_brand`：文章库真实列表，返回吸收状态、确认时间、提炼结果数和正式知识数
- `POST /v1/xhs/article-versions/{version_id}/review`：保存运营经理审核与局部批注
- `POST /v1/xhs/article-versions/{version_id}/approve-example`：批准为正例、反例或竞品参考
- `GET /v1/xhs/ingestion-batches/{batch_id}`：查看批量导入结果
- `POST /v1/xhs/parse-url`：解析公开小红书URL的标题、正文、作者、话题、时间、互动数和全部图片

### 低操作教学

- `POST /v1/xhs/learning-sessions`：一键上传素材并自动分析
- `GET /v1/xhs/learning-sessions/{session_id}`：只突出需要重点确认的洞察
- `POST /v1/xhs/learning-sessions/{session_id}/confirm`：整批确认，少数例外可拒绝或修正
- `GET /v1/brands/{brand_code}/learning-queue`：返回AI学习、确认、向量任务与真实Embedding写入进度

### 大模型设置（已为未来前端提供API，前端本身未开发）

- `PUT /v1/brands/{brand_code}/ai-settings`
- `GET /v1/brands/{brand_code}/ai-settings/{purpose}`
- `POST /v1/brands/{brand_code}/ai-settings/{purpose}/test`

## 七、文章摄入和知识沉淀逻辑

1. 上传文章时，同时写入原始来源和文章专用表。
2. 使用 `external_id`、`platform_note_id`和内容SHA-256进行身份识别、版本更新和去重。
3. 保留Emoji、话题和原始自然段落。
4. 文章按整体、标题、开头、正文、结尾和话题拆分。
5. 每个片段同时保存：
   - `original_text`：达人真实原文；
   - `embedding_text`：加入品牌、产品、达人类型、稿件版本、内容位置后的上下文增强文本。
6. 运营经理提交批注后，保存原文、改文、原因、问题码、严重程度和罸��:����k�w��CONFLICT (article_version_id, ordinal) DO UPDATE
                SET asset_id=excluded.asset_id, source_url=excluded.source_url,
                    status='stored', error_message=NULL, updated_at=now()
                RETURNING id
                """,
                (article_version_id, asset["id"], ordinal, source_url),
            ).fetchone()
            stored += 1
            assets.append({**dict(asset), "link_id": link["id"], "ordinal": ordinal})
            conn.execute(
                """INSERT INTO kb_jobs(brand_id,job_type,entity_type,entity_id,payload,max_attempts)
                   SELECT %s,'analyze_image','asset',%s,%s::jsonb,3
                   WHERE NOT EXISTS (
                     SELECT 1 FROM kb_jobs WHERE job_type='analyze_image' AND entity_id=%s
                       AND payload->>'article_version_id'=%s AND status IN ('pending','running','succeeded')
                   )""",
                (version["brand_id"], asset["id"],
                 __import__("json").dumps({"article_version_id": str(article_version_id), "ordinal": ordinal}),
                 asset["id"], str(article_version_id)),
            )
        except Exception as exc:
            failed += 1
            conn.execute(
                """
                INSERT INTO xhs_article_assets(
                    article_version_id, ordinal, source_url, status, error_message
                ) VALUES (%s,%s,%s,'failed',%s)
                ON CONFLICT (article_version_id, ordinal) DO UPDATE
                SET asset_id=NULL, source_url=excluded.source_url,
                    status='failed', error_message=excluded.error_message, updated_at=now()
                """,
                (article_version_id, ordinal, source_url, str(exc)[:1000]),
            )
    return {"total": len(image_urls), "stored": stored, "failed": failed, "assets": assets}


def list_article_images(conn: Connection, article_version_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT link.id, link.ordinal, link.source_url, link.status, link.error_message,
               link.created_at, asset.id AS asset_id, asset.mime_type,
               asset.width, asset.height, asset.content_hash,
               analysis.id AS analysis_id, analysis.status AS analysis_status,
               analysis.asset_role, analysis.visual_type, analysis.summary AS analysis_summary,
               analysis.ocr_text, analysis.product_exposure, analysis.aesthetic,
               analysis.content_functions, analysis.brand_fit_score, analysis.cover_click_score,
               analysis.selling_power_score, analysis.compliance_risks,
               analysis.reusable_visual_rules, analysis.confidence AS analysis_confidence,
               analysis.error_message AS analysis_error,
               coalesce(vectors.vector_count,0)::int AS multimodal_vector_count
        FROM xhs_article_assets link
        LEFT JOIN kb_assets asset ON asset.id = link.asset_id
        LEFT JOIN xhs_image_analyses analysis ON analysis.asset_id=asset.id
          AND analysis.article_version_id=link.article_version_id
        LEFT JOIN LATERAL (
          SELECT count(*) AS vector_count FROM kb_multimodal_embeddings vector
          WHERE vector.asset_id=asset.id AND vector.article_version_id=link.article_version_id AND vector.active=true
        ) vectors ON true
        WHERE link.article_version_id = %s
        ORDER BY link.ordinal
        """,
        (article_version_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def queue_article_image_analysis(conn: Connection, article_version_id: UUID, force: bool = False) -> dict[str, Any]:
    """为已保存图片创建理解任务；默认跳过已完成结果。"""
    rows = conn.execute(
        """SELECT link.asset_id,link.ordinal,article.brand_id
           FROM xhs_article_assets link JOIN xhs_article_versions version ON version.id=link.article_version_id
           JOIN xhs_articles article ON article.id=version.article_id
           WHERE link.article_version_id=%s AND link.status='stored' AND link.asset_id IS NOT NULL""",
        (article_version_id,),
    ).fetchall()
    queued = skipped = 0
    for row in rows:
        if force:
            # 同一张去重图片可能被多篇文章复用，强制重学不能误删其他文章的任务。
            conn.execute(
                """DELETE FROM kb_jobs WHERE entity_id=%s
                   AND job_type IN ('analyze_image','embed_image') AND status<>'running'
                   AND payload->>'article_version_id'=%s""",
                (row["asset_id"], str(article_version_id)),
            )
            conn.execute("DELETE FROM xhs_image_analyses WHERE asset_id=%s AND article_version_id=%s", (row["asset_id"],article_version_id))
        exists = conn.execute(
            """SELECT 1 FROM kb_jobs WHERE entity_id=%s AND job_type='analyze_image'
               AND payload->>'article_version_id'=%s AND status IN ('pending','running','succeeded')""",
            (row["asset_id"],str(article_version_id)),
        ).fetchone()
        if exists:
            skipped += 1; continue
        conn.execute(
            """INSERT INTO kb_jobs(brand_id,job_type,entity_type,entity_id,payload,max_attempts)
               VALUES (%s,'analyze_image','asset',%s,%s::jsonb,3)""",
            (row["brand_id"],row["asset_id"],__import__("json").dumps({"article_version_id":str(article_version_id),"ordinal":row["ordinal"]})),
        )
        queued += 1
    return {"article_version_id":article_version_id,"total_images":len(rows),"queued":queued,"skipped":skipped}


def resolve_asset_path(conn: Connection, asset_id: UUID) -> tuple[Path, str]:
    asset = conn.execute(
        "SELECT storage_uri, mime_type FROM kb_assets WHERE id=%s", (asset_id,)
    ).fetchone()
    if not asset:
        raise ValueError("图片资产不存在。")
    root = Path(settings.asset_storage_dir).resolve()
    path = (root / asset["storage_uri"]).resolve()
    if root not in path.parents or not path.is_file():
        raise ValueError("图片文件不存在。")
    return path, asset["mime_type"] or "application/octet-stream"
