"""文本向量服务。

生产模式调用兼容 OpenAI Embeddings 的 HTTP 接口。
开发模式在没有密钥时可以生成确定性伪向量，只用于验证数据流程，
绝不能用于评价真实检索质量。
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import urllib.error
import urllib.request

from app.config import settings


class EmbeddingError(RuntimeError):
    pass


def _deterministic_vector(text: str, dimensions: int) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], "big")
    rng = random.Random(seed)
    values = [rng.uniform(-1.0, 1.0) for _ in range(dimensions)]
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def _request_json(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.embedding_api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=settings.embedding_timeout_seconds
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise EmbeddingError(f"向量服务返回 HTTP {exc.code}：{error_body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise EmbeddingError(f"无法连接向量服务：{exc.reason}") from exc


def embed_text(text: str, input_type: str = "document") -> list[float]:
    if not settings.embedding_api_key:
        if settings.allow_deterministic_dev_embedding:
            return _deterministic_vector(text, settings.embedding_dimensions)
        raise EmbeddingError("未配置 EMBEDDING_API_KEY，且开发伪向量已禁用。")

    if input_type not in {"query", "document"}:
        raise EmbeddingError(f"不支持的文本类型：{input_type}")

    if settings.embedding_provider == "dashscope":
        if not settings.dashscope_base_url:
            raise EmbeddingError("未配置 DASHSCOPE_BASE_URL。")
        parameters = {
            "dimension": settings.embedding_dimensions,
            "text_type": input_type,
        }
        if input_type == "query" and settings.embedding_query_instruction:
            parameters["instruct"] = settings.embedding_query_instruction
        result = _request_json(
            f"{settings.dashscope_base_url}/services/embeddings/text-embedding/text-embedding",
            {
                "model": settings.embedding_model,
                "input": {"texts": [text]},
                "parameters": parameters,
            },
        )
        try:
            vector = result["output"]["embeddings"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as exc:
            raise EmbeddingError("DashScope向量响应格式不符合预期。") from exc
    else:
        result = _request_json(
            f"{settings.embedding_base_url}/embeddings",
            {
            "model": settings.embedding_model,
            "input": text,
            "dimensions": settings.embedding_dimensions,
            "encoding_format": "float",
            },
        )
        try:
            vector = result["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as exc:
            raise EmbeddingError("兼容向量服务响应格式不符合预期。") from exc

    if len(vector) != settings.embedding_dimensions:
        raise EmbeddingError(
            f"向量维度错误：期望 {settings.embedding_dimensions}，实际 {len(vector)}。"
        )
    return vector
