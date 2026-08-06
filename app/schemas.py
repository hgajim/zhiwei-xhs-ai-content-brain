"""API 请求与响应结构。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class BrandCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    timezone: str = "Asia/Shanghai"


class SourceCreate(BaseModel):
    brand_code: str
    source_type: str
    external_id: str | None = None
    title: str
    text: str | None = None
    original_uri: str | None = None
    storage_uri: str | None = None
    mime_type: str | None = "text/plain"
    owner: str | None = None
    authority_level: int = Field(default=5, ge=1, le=6)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChunkInput(BaseModel):
    chunk_type: str
    text: str = Field(min_length=1)
    search_terms: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeCreate(BaseModel):
    brand_code: str
    canonical_key: str
    knowledge_type: str
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source_version_id: UUID | None = None
    authority_level: int = Field(default=6, ge=1, le=6)
    confidence: float | None = Field(default=None, ge=0, le=1)
    scope: dict[str, Any] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)
    chunks: list[ChunkInput] = Field(default_factory=list)


class KnowledgeApprove(BaseModel):
    approved_by: str
    authority_level: int = Field(ge=1, le=5)
    confidence: float = Field(ge=0, le=1)
    scope: dict[str, Any] | None = None
    attributes: dict[str, Any] | None = None


class SearchRequest(BaseModel):
    brand_code: str
    query: str = Field(min_length=1)
    segmented_query: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)
    knowledge_types: list[str] = Field(default_factory=list)
    top_k: int = Field(default=12, ge=1, le=50)
    semantic_candidates: int = Field(default=40, ge=10, le=200)
    lexical_candidates: int = Field(default=40, ge=10, le=200)


class SearchResult(BaseModel):
    chunk_id: UUID
    version_id: UUID
    item_id: UUID
    knowledge_type: str
    canonical_key: str
    title: str
    chunk_type: str
    text: str
    score: float
    authority_level: int
    confidence: float | None
    scope: dict[str, Any]
    attributes: dict[str, Any]
    source_title: str | None
    source_version: int | None
    approved_by: str | None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


class XhsArticleImport(BaseModel):
    """单篇小红书文章或稿件版本。"""

    brand_code: str
    article_type: Literal[
        "creator_submission",
        "approved_creator_content",
        "published_creator_content",
        "competitor_content",
        "brand_owned_content",
    ]
    version_type: Literal[
        "creator_original",
        "reviewer_revision",
        "creator_revision",
        "approved_final",
        "published",
    ]
    platform_note_id: str | None = None
    external_id: str | None = None
    creator_id: str | None = None
    creator_name: str | None = None
    creator_type: str | None = None
    product_code: str | None = None
    campaign_code: str | None = None
    content_type: str | None = None
    source_url: str | None = None
    published_at: datetime | None = None
    title: str = Field(default="", max_length=300)
    body: str = Field(default="", max_length=100000)
    hashtags: list[str] = Field(default_factory=list)
    mentioned_products: list[str] = Field(default_factory=list)
    authority_level: int = Field(default=5, ge=1, le=6)
    metadata: dict[str, Any] = Field(default_factory=dict)
    version_metadata: dict[str, Any] = Field(default_factory=dict)


class XhsArticleBatchImport(BaseModel):
    brand_code: str
    batch_name: str | None = None
    articles: list[XhsArticleImport] = Field(min_length=1, max_length=500)


class XhsExampleApprove(BaseModel):
    example_kind: Literal["positive", "negative", "competitor_reference"]
    approved_by: str
    authority_level: int = Field(default=2, ge=1, le=5)
    confidence: float = Field(default=0.95, ge=0, le=1)
    summary: str | None = None
    review_reason: str | None = None
    scope: dict[str, Any] = Field(default_factory=dict)


class ReviewAnnotationInput(BaseModel):
    location_type: Literal["title", "body_span", "image_region", "video_segment", "overall"]
    location_data: dict[str, Any] = Field(default_factory=dict)
    original_text: str | None = None
    revised_text: str | None = None
    decision: Literal["keep", "rewrite", "delete", "reject", "review"]
    reason: str = Field(min_length=1)
    reason_codes: list[str] = Field(default_factory=list)
    severity: Literal["low", "medium", "high", "critical"] | None = None
    reviewer_confidence: float | None = Field(default=None, ge=0, le=1)
    linked_rule_version_id: UUID | None = None


class XhsArticleReview(BaseModel):
    reviewer: str
    overall_decision: Literal["approve", "minor_revision", "major_revision", "reject"]
    annotations: list[ReviewAnnotationInput] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    distill_annotations: bool = True


class XhsTeachingArticle(BaseModel):
    """教学接口中的文章；品牌只在外层填写一次。"""

    article_type: Literal[
        "creator_submission", "approved_creator_content", "published_creator_content",
        "competitor_content", "brand_owned_content",
    ] = "creator_submission"
    version_type: Literal[
        "creator_original", "reviewer_revision", "creator_revision", "approved_final", "published",
    ] = "creator_original"
    platform_note_id: str | None = None
    external_id: str | None = None
    creator_id: str | None = None
    creator_name: str | None = None
    creator_type: str | None = None
    product_code: str | None = None
    campaign_code: str | None = None
    content_type: str | None = None
    source_url: str | None = None
    title: str = Field(default="", max_length=300)
    body: str = Field(default="", max_length=100000)
    hashtags: list[str] = Field(default_factory=list)
    mentioned_products: list[str] = Field(default_factory=list)
    authority_level: int = Field(default=5, ge=1, le=6)
    metadata: dict[str, Any] = Field(default_factory=dict)
    version_metadata: dict[str, Any] = Field(default_factory=dict)


class XhsLearningCreate(BaseModel):
    """一次低操作教学：素材＋可选的一句话，其他工作交给AI。"""

    brand_code: str
    learning_mode: Literal["positive_example", "negative_example", "revision_pair", "experience"]
    original_article: XhsTeachingArticle | None = None
    revised_article: XhsTeachingArticle | None = None
    user_feedback: str | None = None
    image_context: list[dict[str, Any]] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = None


class XhsImageIngest(BaseModel):
    """手动重试或补充文章图片；不传URL时读取文章元数据中的图片地址。"""

    urls: list[str] | None = Field(default=None, max_length=30)


class XhsArticleForget(BaseModel):
    """保留原文，仅遗忘由文章学习产生的知识。"""

    forgotten_by: str = Field(min_length=1)
    reason: str | None = None


class UserRegister(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(default="", max_length=80)


class UserLogin(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)

class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=5,max_length=254)

class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=20)
    new_password: str = Field(min_length=10,max_length=128)

class AiReviewCreate(BaseModel):
    brand_code: str
    title: str = Field(default="",max_length=300)
    body: str = Field(min_length=1,max_length=100000)
    image_context: list[dict[str,Any]] = Field(default_factory=list)
    created_by: str | None = None
    compare: bool = False

class AiReviewAbsorb(BaseModel):
    confirmed_by: str

class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1,max_length=80)
    description: str = Field(default="",max_length=500)


class LearningCorrection(BaseModel):
    insight_id: UUID
    correction: str = Field(min_length=1)


class XhsLearningConfirm(BaseModel):
    """默认接受整批，只提交需要拒绝或改正的少数例外。"""

    confirmed_by: str
    publish_to_retrieval: bool = True
    rejected_insight_ids: list[UUID] = Field(default_factory=list)
    corrections: list[LearningCorrection] = Field(default_factory=list)


class AiSettingUpsert(BaseModel):
    purpose: Literal["content_learning", "content_review", "knowledge_governance"] = "content_learning"
    provider: str = "openai_compatible"
    base_url: str = Field(min_length=8)
    model_name: str = Field(min_length=1)
    api_key: str | None = Field(default=None, min_length=1)
    enabled: bool = True
    extra_options: dict[str, Any] = Field(default_factory=dict)


class XhsUrlParse(BaseModel):
    url: str = Field(min_length=20, max_length=2000)
