"""将带 TOML 头信息的 Markdown 批量导入为候选知识。

示例：
    python -m scripts.import_markdown --brand demo_brand --path examples/knowledge
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.db import close_pool, open_pool, transaction
from app.services.knowledge import create_knowledge, create_source
from app.services.markdown import parse_markdown


def import_file(conn, brand_code: str, path: Path) -> dict:
    metadata, content = parse_markdown(path)
    required = {"canonical_key", "knowledge_type", "title"}
    missing = sorted(required - metadata.keys())
    if missing:
        raise ValueError(f"{path} 缺少字段：{', '.join(missing)}")

    source = create_source(
        conn,
        {
            "brand_code": brand_code,
            "source_type": "manual_entry",
            "external_id": str(path.resolve()),
            "title": metadata["title"],
            "text": content,
            "original_uri": str(path.resolve()),
            "authority_level": int(metadata.get("authority_level", 6)),
            "metadata": {"import_format": "markdown_toml"},
        },
    )
    return create_knowledge(
        conn,
        {
            "brand_code": brand_code,
            "canonical_key": metadata["canonical_key"],
            "knowledge_type": metadata["knowledge_type"],
            "title": metadata["title"],
            "summary": metadata.get("summary", metadata["title"]),
            "content": content,
            "source_version_id": source["source_version"]["id"],
            "authority_level": int(metadata.get("authority_level", 6)),
            "confidence": float(metadata["confidence"]) if "confidence" in metadata else None,
            "scope": metadata.get("scope", {}),
            "attributes": metadata.get("attributes", {}),
            "chunks": [],
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="批量导入品牌 Markdown 知识")
    parser.add_argument("--brand", required=True, help="品牌编码")
    parser.add_argument("--path", required=True, help="Markdown 文件或目录")
    args = parser.parse_args()

    target = Path(args.path)
    files = [target] if target.is_file() else sorted(target.rglob("*.md"))
    if not files:
        raise SystemExit("没有找到 Markdown 文件。")

    open_pool()
    try:
        with transaction() as conn:
            for path in files:
                result = import_file(conn, args.brand, path)
                print(f"已导入候选知识：{path.name} -> {result['version']['id']}")
    finally:
        close_pool()


if __name__ == "__main__":
    main()
