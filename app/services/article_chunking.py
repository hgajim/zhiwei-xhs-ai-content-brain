"""小红书文章结构化切分与Embedding上下文增强。"""

from __future__ import annotations

import re
from typing import Any

from app.services.chunking import normalize_text, segment_for_search, semantic_chunks


def normalize_hashtag(tag: str) -> str:
    """保留话题文字，去除首尾井号与多余空格。"""
    return re.sub(r"\s+", "", tag.strip().strip("#＃"))


def normalize_article(title: str, body: str, hashtags: list[str]) -> tuple[str, str, list[str]]:
    normalized_title = normalize_text(title)
    normalized_body = normalize_text(body)
    normalized_hashtags = [normalize_hashtag(tag) for tag in hashtags]
    normalized_hashtags = [tag for tag in dict.fromkeys(normalized_hashtags) if tag]
    full_text = "\n\n".join(
        part for part in [normalized_title, normalized_body] if part
    )
    if normalized_hashtags:
        full_text += "\n\n" + " ".join(f"#{tag}" for tag in normalized_hashtags)
    return normalized_title, normalized_body, normalized_hashtags


def _context_prefix(context: dict[str, Any], position: str) -> str:
    fields = [
        ("知识用途", context.get("knowledge_purpose", "小红书合作达人文章案例")),
        ("品牌", context.get("brand_name")),
        ("文章类型", context.get("article_type")),
        ("产品", context.get("product_code")),
        ("达人类型", context.get("creator_type")),
        ("内容类型", context.get("content_type")),
        ("稿件版本", context.get("version_type")),
        ("内容位置", position),
    ]
    return "\n".join(f"{label}：{value}" for label, value in fields if value)


def _chunk(
    chunk_type: str,
    original_text: str,
    context: dict[str, Any],
    position: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prefix = _context_prefix(context, position)
    embedding_text = f"{prefix}\n\n内容：\n{original_text}" if prefix else original_text
    return {
        "chunk_type": chunk_type,
        "original_text": original_text,
        "embedding_text": embedding_text,
        "search_terms": segment_for_search(f"{prefix} {original_text}"),
        "metadata": metadata or {},
    }


def build_article_chunks(
    title: str,
    body: str,
    hashtags: list[str],
    context: dict[str, Any],
    max_chars: int = 900,
) -> list[dict[str, Any]]:
    """同时生成文章整体、标题、语义段落和话题片段。"""
    chunks: list[dict[str, Any]] = []
    full_text = "\n\n".join(part for part in [title, body] if part)
    if hashtags:
        full_text += "\n\n" + " ".join(f"#{tag}" for tag in hashtags)
    if full_text:
        chunks.append(_chunk("article_full", full_text, context, "文章整体"))
    if title:
        chunks.append(_chunk("article_title", title, context, "标题"))

    paragraphs: list[str] = []
    if body:
        # 先尊重达人原稿的自然段落；只有单段过长时才继续语义切分。
        for raw_paragraph in re.split(r"\n\s*\n", body):
            raw_paragraph = raw_paragraph.strip()
            if not raw_paragraph:
                continue
            if len(raw_paragraph) <= max_chars:
                paragraphs.append(raw_paragraph)
            else:
                paragraphs.extend(semantic_chunks(raw_paragraph, max_chars=max_chars))
    for index, paragraph in enumerate(paragraphs):
        if index == 0:
            chunk_type, position = "article_opening", "开头"
        elif index == len(paragraphs) - 1 and len(paragraphs) >= 3:
            chunk_type, position = "article_closing", "结尾"
        else:
            chunk_type, position = "article_body", "正文"
        chunks.append(
            _chunk(
                chunk_type,
                paragraph,
                context,
                position,
                {"paragraph_index": index},
            )
        )

    if hashtags:
        hashtag_text = " ".join(f"#{tag}" for tag in hashtags)
        chunks.append(_chunk("article_hashtags", hashtag_text, context, "话题标签"))
    return chunks
