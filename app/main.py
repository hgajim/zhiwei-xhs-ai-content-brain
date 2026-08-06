"""知识库 HTTP API。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.db import close_pool, open_pool, transaction
from app.schemas import (
    BrandCreate,
    KnowledgeApprove,
    KnowledgeCreate,
    SearchRequest,
    SearchResponse,
    SourceCreate,
    XhsArticleBatchImport,
    XhsArticleImport,
    XhsArticleReview,
    XhsExampleApprove,
    XhsLearningConfirm,
    XhsLearningCreate,
    XhsImageIngest,
    XhsArticleForget,
    AiSettingUpsert,
    XhsUrlParse,
    UserRegister,
    UserLogin,
    PasswordResetRequest,
    PasswordResetConfirm,
    AiReviewCreate,
    AiReviewAbsorb,
    WorkspaceCreate,
)
from app.services.articles import (
    approve_article_as_example,
    create_article,
    get_article,
    list_articles,
    submit_article_review,
)
from app.services.knowledge import (
    approve_knowledge,
    create_brand,
    create_knowledge,
    create_source,
)
from app.services.search import hybrid_search
from app.services.learning import (
    confirm_learning_session,
    create_learning_session,
    enqueue_learning_session,
    get_learning_session,
)
from app.services.ai_settings import delete_ai_setting, get_ai_setting, upsert_ai_setting
from app.services.llm import structured_chat
from app.services.xhs_url import parse_xhs_url
from app.services.assets import ingest_article_images, list_article_images, queue_article_image_analysis, resolve_asset_path
from app.services.queue_status import get_learning_queue
from app.services.forgetting import (
    delete_article_with_knowledge,
    forget_article_knowledge,
    preview_delete_article,
    preview_forget_article_knowledge,
)
from app.services.auth import authenticate, login, register, user_context, token_hash, hash_password, normalize_email, authorize_brand, authorize_entity
from app.services.ai_review import create_ai_review, create_ai_review_comparison, get_ai_review
from app.services.absorption_health import calculate_absorption_health


@asynccontextmanager
async def lifespan(_: FastAPI):
    open_pool()
    yield
    close_pool()


app = FastAPI(
    title="品牌小红书动态知识库",
    version="0.1.0",
    description="提供知识导入、审批、版本化和混合检索接口。",
    lifespan=lifespan,
)

@app.middleware('http')
async def require_api_identity(request:Request,call_next):
    path=request.url.path
    if request.method=='OPTIONS' or not path.startswith('/v1/') or path.startswith('/v1/auth/'):
        return await call_next(request)
    try:
        with transaction() as conn:
            authorization=request.headers.get('authorization')
            if not authorization and request.cookies.get('zhiwei_session'):
                authorization=f"Bearer {request.cookies['zhiwei_session']}"
            user=authenticate(conn,authorization);request.state.user=user
            import re
            brand_match=re.search(r'/v1/brands/([^/]+)',path)
            brand_code=brand_match.group(1) if brand_match else request.query_params.get('brand_code')
            if not brand_code and request.headers.get('content-type','').startswith('application/json') and request.method in {'POST','PUT','PATCH'}:
                try: brand_code=(await request.json()).get('brand_code')
                except Exception: brand_code=None
            if brand_code:authorize_brand(conn,user['id'],brand_code)
            patterns=[(r'/v1/xhs/articles/([0-9a-f-]{36})','article'),(r'/v1/xhs/article-versions/([0-9a-f-]{36})','article_version'),(r'/v1/xhs/learning-sessions/([0-9a-f-]{36})','learning_session'),(r'/v1/xhs/ai-reviews/([0-9a-f-]{36})','ai_review'),(r'/v1/assets/([0-9a-f-]{36})','asset')]
            for pattern,kind in patterns:
                match=re.search(pattern,path)
                if match:authorize_entity(conn,user['id'],kind,match.group(1));break
    except ValueError as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=401 if '登录' in str(exc) else 403,content={'detail':str(exc)})
    return await call_next(request)


@app.post("/v1/auth/register")
def post_register(payload: UserRegister, request: Request) -> dict:
    try:
        with transaction() as conn:
            return register(conn,payload.email,payload.password,payload.display_name)
    except ValueError as exc: raise HTTPException(status_code=400,detail=str(exc)) from exc


@app.post("/v1/auth/login")
def post_login(payload: UserLogin, request: Request, response: Response) -> dict:
    try:
        with transaction() as conn:
            result=login(conn,payload.email,payload.password,request.headers.get('user-agent'),request.client.host if request.client else None)
            response.set_cookie('zhiwei_session',result['access_token'],httponly=True,samesite='lax',max_age=30*24*60*60,path='/')
            return result
    except ValueError as exc: raise HTTPException(status_code=401,detail=str(exc)) from exc


@app.get("/v1/auth/me")
def get_me(response: Response, authorization: str | None = Header(default=None)) -> dict:
    try:
        with transaction() as conn:
            user=authenticate(conn,authorization); context=user_context(conn,user['id'])
            if authorization and authorization.lower().startswith('bearer '):
                response.set_cookie('zhiwei_session',authorization.split(' ',1)[1],httponly=True,samesite='lax',max_age=30*24*60*60,path='/')
            return {'user':{k:user[k] for k in ('id','email','display_name','is_admin')},**context}
    except ValueError as exc: raise HTTPException(status_code=401,detail=str(exc)) from exc

@app.post('/v1/workspaces')
def post_workspace(payload:WorkspaceCreate,authorization:str|None=Header(default=None))->dict:
    try:
        with transaction() as conn:
            user=authenticate(conn,authorization)
            workspace=conn.execute('INSERT INTO workspaces(owner_user_id,name,description) VALUES(%s,%s,%s) RETURNING id,name,description,status',(user['id'],payload.name,payload.description)).fetchone()
            conn.execute("INSERT INTO workspace_members(workspace_id,user_id,role) VALUES(%s,%s,'owner')",(workspace['id'],user['id']))
            code=f"ws_{str(workspace['id']).replace('-','')[:16]}";brand=conn.execute('INSERT INTO brands(code,name,workspace_id) VALUES(%s,%s,%s) RETURNING code',(code,payload.name,workspace['id'])).fetchone()
            return {**workspace,'brand_code':brand['code'],'role':'owner'}
    except ValueError as exc:raise HTTPException(status_code=401,detail=str(exc)) from exc


@app.post("/v1/auth/logout")
def post_logout(response: Response, authorization: str | None = Header(default=None)) -> dict:
    if authorization and authorization.lower().startswith('bearer '):
        with transaction() as conn: conn.execute('UPDATE auth_sessions SET revoked_at=now() WHERE token_hash=%s',(token_hash(authorization.split(' ',1)[1]),))
    response.delete_cookie('zhiwei_session',path='/')
    return {'status':'logged_out'}

@app.post('/v1/auth/password-reset/request')
def request_password_reset(payload:PasswordResetRequest)->dict:
    import secrets
    from datetime import datetime,timedelta,timezone
    with transaction() as conn:
        user=conn.execute('SELECT id FROM app_users WHERE lower(email)=%s',(normalize_email(payload.email),)).fetchone()
        if not user:return {'status':'accepted'}
        token=secrets.token_urlsafe(36)
        conn.execute('INSERT INTO password_reset_tokens(user_id,token_hash,expires_at) VALUES(%s,%s,%s)',(user['id'],token_hash(token),datetime.now(timezone.utc)+timedelta(hours=1)))
        return {'status':'accepted','development_reset_token':token}

@app.post('/v1/auth/password-reset/confirm')
def confirm_password_reset(payload:PasswordResetConfirm)->dict:
    with transaction() as conn:
        row=conn.execute('SELECT * FROM password_reset_tokens WHERE token_hash=%s AND used_at IS NULL AND expires_at>now() FOR UPDATE',(token_hash(payload.token),)).fetchone()
        if not row:raise HTTPException(status_code=400,detail='重置链接无效或已过期。')
        conn.execute('UPDATE app_users SET password_hash=%s,updated_at=now() WHERE id=%s',(hash_password(payload.new_password),row['user_id']))
        conn.execute('UPDATE password_reset_tokens SET used_at=now() WHERE id=%s',(row['id'],));conn.execute('UPDATE auth_sessions SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL',(row['user_id'],))
    return {'status':'password_reset'}

@app.get('/v1/admin/summary')
def admin_summary(authorization:str|None=Header(default=None))->dict:
    try:
        with transaction() as conn:
            user=authenticate(conn,authorization)
            if not user['is_admin']:raise HTTPException(status_code=403,detail='无管理员权限。')
            return {k:conn.execute(sql).fetchone()['count'] for k,sql in {
              'users':'SELECT count(*) count FROM app_users','workspaces':'SELECT count(*) count FROM workspaces',
              'articles':'SELECT count(*) count FROM xhs_articles','failed_jobs':"SELECT count(*) count FROM kb_jobs WHERE status='failed'"}.items()}
    except ValueError as exc:raise HTTPException(status_code=401,detail=str(exc)) from exc

@app.post('/v1/xhs/ai-reviews')
def post_ai_review(payload:AiReviewCreate)->dict:
    try:
        with transaction() as conn:
            data=payload.model_dump()
            return create_ai_review_comparison(conn,data) if payload.compare else create_ai_review(conn,data)
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc
    except Exception as exc:raise HTTPException(status_code=502,detail=f'AI审核失败：{exc}') from exc

@app.get('/v1/xhs/ai-reviews/{review_id}')
def get_ai_review_run(review_id:UUID)->dict:
    try:
        with transaction() as conn:return get_ai_review(conn,review_id)
    except ValueError as exc:raise HTTPException(status_code=404,detail=str(exc)) from exc

@app.post('/v1/xhs/ai-reviews/{review_id}/absorb')
def absorb_ai_review(review_id:UUID,payload:AiReviewAbsorb)->dict:
    try:
        with transaction() as conn:
            review=get_ai_review(conn,review_id)
            if review['absorbed_session_id']:return {'status':'already_absorbed','session_id':review['absorbed_session_id']}
            code=conn.execute('SELECT code FROM brands WHERE id=%s',(review['brand_id'],)).fetchone()['code']
            feedback='；'.join(item.get('problem','')+'→'+item.get('suggestion','') for item in review['issues'])
            result=create_learning_session(conn,{'brand_code':code,'learning_mode':'revision_pair','user_feedback':feedback,'created_by':payload.confirmed_by,'original_article':{'external_id':f'review-{review_id}','article_type':'creator_submission','version_type':'creator_original','title':review['title'],'body':review['original_text']},'revised_article':{'external_id':f'review-{review_id}','article_type':'creator_submission','version_type':'approved_final','title':review['title'],'body':review['revised_text']}})
            session=result['session']
            if session['status']!='confirmed':confirmation=confirm_learning_session(conn,session['id'],{'confirmed_by':payload.confirmed_by,'publish_to_retrieval':True,'rejected_insight_ids':[],'corrections':[]})
            conn.execute('UPDATE xhs_ai_review_runs SET absorbed_session_id=%s WHERE id=%s',(session['id'],review_id))
            return {'status':'absorbed','session_id':session['id']}
    except ValueError as exc:raise HTTPException(status_code=400,detail=str(exc)) from exc

# 本地前端开发地址；正式网页部署时通过环境配置收紧允许来源。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    try:
        with transaction() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "message": "数据库连接正常"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"数据库不可用：{exc}") from exc


@app.post("/v1/brands")
def post_brand(payload: BrandCreate) -> dict:
    with transaction() as conn:
        return create_brand(conn, payload.code, payload.name, payload.timezone)


@app.post("/v1/sources")
def post_source(payload: SourceCreate) -> dict:
    try:
        with transaction() as conn:
            return create_source(conn, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/knowledge")
def post_knowledge(payload: KnowledgeCreate) -> dict:
    try:
        with transaction() as conn:
            return create_knowledge(conn, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/knowledge/{version_id}/approve")
def post_approve(version_id: UUID, payload: KnowledgeApprove) -> dict:
    try:
        with transaction() as conn:
            return approve_knowledge(conn, version_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/search", response_model=SearchResponse)
def post_search(payload: SearchRequest) -> SearchResponse:
    try:
        with transaction() as conn:
            rows = hybrid_search(conn, payload.model_dump())
        return SearchResponse(query=payload.query, results=rows)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/xhs/articles")
def post_xhs_article(payload: XhsArticleImport) -> dict:
    """导入一篇达人稿、品牌文章或竞品文章。"""
    try:
        with transaction() as conn:
            return create_article(conn, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/xhs/articles/batch")
def post_xhs_articles_batch(payload: XhsArticleBatchImport) -> dict:
    """批量导入文章；单篇失败不会回滚整个批次。"""
    with transaction() as conn:
        brand = conn.execute(
            "SELECT id FROM brands WHERE code = %s", (payload.brand_code,)
        ).fetchone()
        if not brand:
            raise HTTPException(status_code=400, detail=f"品牌不存在：{payload.brand_code}")
        batch = conn.execute(
            """
            INSERT INTO xhs_ingestion_batches(brand_id, batch_name, total_count)
            VALUES (%s, %s, %s) RETURNING id
            """,
            (brand["id"], payload.batch_name, len(payload.articles)),
        ).fetchone()

    inserted = deduplicated = failed = 0
    for index, article_payload in enumerate(payload.articles):
        data = article_payload.model_dump()
        data["brand_code"] = payload.brand_code
        try:
            with transaction() as conn:
                result = create_article(conn, data)
                item_status = "deduplicated" if result["deduplicated"] else "inserted"
                deduplicated += int(result["deduplicated"])
                inserted += int(not result["deduplicated"])
                conn.execute(
                    """
                    INSERT INTO xhs_ingestion_items(
                        batch_id, input_index, external_id, status,
                        article_id, article_version_id
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        batch["id"], index, data.get("external_id"), item_status,
                        result["article_id"], result["article_version_id"],
                    ),
                )
        except Exception as exc:
            failed += 1
            with transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO xhs_ingestion_items(
                        batch_id, input_index, external_id, status, error_message
                    ) VALUES (%s, %s, %s, 'failed', %s)
                    """,
                    (batch["id"], index, data.get("external_id"), str(exc)[:2000]),
                )

    status = "succeeded" if failed == 0 else ("failed" if failed == len(payload.articles) else "partial_success")
    with transaction() as conn:
        conn.execute(
            """
            UPDATE xhs_ingestion_batches
            SET status = %s, inserted_count = %s, deduplicated_count = %s,
                failed_count = %s, completed_at = now()
            WHERE id = %s
            """,
            (status, inserted, deduplicated, failed, batch["id"]),
        )
    return {
        "batch_id": batch["id"], "status": status,
        "total": len(payload.articles), "inserted": inserted,
        "deduplicated": deduplicated, "failed": failed,
    }


@app.get("/v1/xhs/articles")
def get_xhs_articles(brand_code: str = "demo_brand", limit: int = 100) -> dict:
    """文章库列表：包含最近一次吸收状态、时间和生成知识数量。"""
    try:
        with transaction() as conn:
            items = list_articles(conn, brand_code, min(max(limit, 1), 500))
        return {"items": items, "total": len(items)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/xhs/articles/{article_id}")
def get_xhs_article(article_id: UUID) -> dict:
    try:
        with transaction() as conn:
            return get_article(conn, article_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/xhs/articles/{article_id}/forget-preview")
def get_xhs_article_forget_preview(article_id: UUID) -> dict:
    """预览仅遗忘派生知识将影响的数据，原始文章和图片始终保留。"""
    try:
        with transaction() as conn:
            return preview_forget_article_knowledge(conn, article_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/v1/xhs/articles/{article_id}/forget-knowledge")
def post_xhs_article_forget_knowledge(article_id: UUID, payload: XhsArticleForget) -> dict:
    """在单一事务中删除文章派生知识、分块、向量和任务，保留原文与图片。"""
    try:
        with transaction() as conn:
            return forget_article_knowledge(
                conn, article_id, payload.forgotten_by, payload.reason
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/xhs/articles/{article_id}/delete-preview")
def get_xhs_article_delete_preview(article_id: UUID) -> dict:
    """删除前返回文章、知识、分块、向量及队列任务的实际影响数量。"""
    try:
        with transaction() as conn:
            return preview_delete_article(conn, article_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/v1/xhs/articles/{article_id}")
def delete_xhs_article(article_id: UUID, request: Request, reason: str | None = None) -> dict:
    """永久删除文章，并在同一事务中同步回退其非共享知识和向量数据。"""
    try:
        user = request.state.user
        deleted_by = user.get("display_name") or user.get("email") or str(user["id"])
        with transaction() as conn:
            return delete_article_with_knowledge(conn, article_id, deleted_by, reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/xhs/article-versions/{version_id}/review")
def post_xhs_article_review(version_id: UUID, payload: XhsArticleReview) -> dict:
    try:
        with transaction() as conn:
            return submit_article_review(conn, version_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/xhs/article-versions/{version_id}/approve-example")
def post_xhs_approve_example(version_id: UUID, payload: XhsExampleApprove) -> dict:
    try:
        with transaction() as conn:
            return approve_article_as_example(conn, version_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/xhs/ingestion-batches/{batch_id}")
def get_xhs_ingestion_batch(batch_id: UUID) -> dict:
    with transaction() as conn:
        batch = conn.execute(
            "SELECT * FROM xhs_ingestion_batches WHERE id = %s", (batch_id,)
        ).fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="导入批次不存在。")
        items = conn.execute(
            "SELECT * FROM xhs_ingestion_items WHERE batch_id = %s ORDER BY input_index",
            (batch_id,),
        ).fetchall()
    return {"batch": batch, "items": items}


@app.post("/v1/xhs/learning-sessions")
def post_xhs_learning_session(payload: XhsLearningCreate) -> dict:
    """一键喂养：上传素材，可选说一句评价，系统自动拆解候选经验。"""
    try:
        with transaction() as conn:
            result = create_learning_session(conn, payload.model_dump())
        version_id = result["session"].get("original_article_version_id")
        if version_id and not result.get("deduplicated"):
            with transaction() as conn:
                result["image_ingestion"] = ingest_article_images(conn, version_id)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI教学分析失败：{exc}") from exc


@app.post("/v1/xhs/learning-sessions/background", status_code=202)
def post_xhs_learning_session_background(payload: XhsLearningCreate) -> dict:
    """立即加入后台队列；不等待AI分析、图片下载、自动吸收和向量化。"""
    try:
        with transaction() as conn:
            return enqueue_learning_session(conn, payload.model_dump(mode="json"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/xhs/article-versions/{version_id}/images/ingest")
def post_xhs_article_images(version_id: UUID, payload: XhsImageIngest) -> dict:
    """下载、校验并持久化文章图片；支持失败后重试。"""
    try:
        with transaction() as conn:
            return ingest_article_images(conn, version_id, payload.urls)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/xhs/article-versions/{version_id}/images")
def get_xhs_article_images(version_id: UUID) -> dict:
    with transaction() as conn:
        items = list_article_images(conn, version_id)
    return {"items": items, "total": len(items)}


@app.post("/v1/xhs/article-versions/{version_id}/images/analyze")
def post_xhs_article_images_analyze(version_id: UUID, force: bool = False) -> dict:
    try:
        with transaction() as conn:
            return queue_article_image_analysis(conn, version_id, force)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/assets/{asset_id}/content")
def get_asset_content(asset_id: UUID):
    try:
        with transaction() as conn:
            path, mime_type = resolve_asset_path(conn, asset_id)
        return FileResponse(path, media_type=mime_type, headers={"Cache-Control": "private, max-age=86400"})
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/brands/{brand_code}/learning-queue")
def get_brand_learning_queue(brand_code: str, limit: int = 30) -> dict:
    """返回AI学习和Embedding写入的可验证进度。"""
    try:
        with transaction() as conn:
            return get_learning_queue(conn, brand_code, min(max(limit, 1), 100))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/brands/{brand_code}/absorption-health")
def get_brand_absorption_health(brand_code: str) -> dict:
    """计算第一阶段吸收健康度，并保留每小时一份趋势快照。"""
    try:
        with transaction() as conn:
            return calculate_absorption_health(conn, brand_code)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/xhs/learning-sessions/{session_id}")
def get_xhs_learning_session(session_id: UUID) -> dict:
    try:
        with transaction() as conn:
            return get_learning_session(conn, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/v1/xhs/learning-sessions/{session_id}/confirm")
def post_xhs_learning_confirm(session_id: UUID, payload: XhsLearningConfirm) -> dict:
    """默认整批接受，用户只提交少数拒绝项或修正项。"""
    try:
        with transaction() as conn:
            return confirm_learning_session(conn, session_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/v1/brands/{brand_code}/ai-settings")
def put_brand_ai_setting(brand_code: str, payload: AiSettingUpsert) -> dict:
    """供未来前端保存模型配置；API Key加密保存且永不回显。"""
    try:
        with transaction() as conn:
            return upsert_ai_setting(conn, brand_code, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/brands/{brand_code}/ai-settings/{purpose}")
def get_brand_ai_setting(brand_code: str, purpose: str) -> dict:
    try:
        with transaction() as conn:
            setting = get_ai_setting(conn, brand_code, purpose)
        if not setting:
            raise HTTPException(status_code=404, detail="该用途尚未配置模型。")
        return setting
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/v1/brands/{brand_code}/ai-settings/{purpose}")
def delete_brand_ai_setting(brand_code: str, purpose: str) -> dict:
    """重置模型配置和加密API Key。"""
    try:
        with transaction() as conn:
            deleted = delete_ai_setting(conn, brand_code, purpose)
        if not deleted:
            raise HTTPException(status_code=404, detail="该用途尚未配置模型。")
        return {"status": "reset", "message": "模型配置和API Key已重置。"}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/brands/{brand_code}/ai-settings/{purpose}/test")
def test_brand_ai_setting(brand_code: str, purpose: str) -> dict:
    """验证地址、模型和密钥是否能实际完成一次JSON响应。"""
    try:
        with transaction() as conn:
            setting = get_ai_setting(conn, brand_code, purpose, include_secret=True)
        if not setting:
            raise HTTPException(status_code=404, detail="该用途尚未配置模型。")
        result = structured_chat(
            "只返回JSON对象。", '返回 {"ok":true}。', model_config=setting
        )
        return {"status": "ok", "model_name": setting["model_name"], "response_valid": bool(result)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"模型连接测试失败：{exc}") from exc


@app.post("/v1/xhs/parse-url")
def post_xhs_parse_url(payload: XhsUrlParse) -> dict:
    """解析公开小红书链接，供前端回填文章和图片信息。"""
    try:
        return parse_xhs_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
