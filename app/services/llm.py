"""用于教学理解的 OpenAI 兼容大模型客户端。"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import settings


class LlmError(RuntimeError):
    pass


def structured_chat(
    system_prompt: str, user_prompt: str, *, model_config: dict[str, Any] | None = None
) -> dict[str, Any]:
    """要求模型返回 JSON；密钥只进入请求头，不进入日志。"""
    model_config = model_config or {}
    api_key = model_config.get("api_key") or settings.llm_api_key or settings.embedding_api_key
    base_url = (model_config.get("base_url") or settings.llm_base_url).rstrip("/")
    model_name = model_config.get("model_name") or settings.llm_model
    if not base_url or not api_key:
        raise LlmError("未配置 LLM_BASE_URL 或可用的 API Key。")
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    request = Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.llm_timeout_seconds) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise LlmError(f"教学理解模型请求失败（HTTP {exc.code}）：{detail}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LlmError(f"教学理解模型请求失败：{exc}") from exc
    try:
        content = result["choices"][0]["message"]["content"]
        return json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise LlmError("教学理解模型没有返回有效的 JSON 结果。") from exc
