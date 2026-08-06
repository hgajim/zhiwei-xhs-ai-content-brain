"""Markdown 知识文件解析，不依赖数据库。"""

from __future__ import annotations

import tomllib
from pathlib import Path

from app.services.chunking import normalize_text


def parse_markdown(path: Path) -> tuple[dict, str]:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("+++\n"):
        raise ValueError(f"{path} 缺少 TOML 头信息起始标记 +++")
    try:
        header, body = raw[4:].split("\n+++\n", 1)
    except ValueError as exc:
        raise ValueError(f"{path} 缺少 TOML 头信息结束标记 +++") from exc
    metadata = tomllib.loads(header)
    return metadata, normalize_text(body)

