"""写入一个品牌和一条示例规则，便于验证完整流程。"""

from __future__ import annotations

from app.db import close_pool, open_pool, transaction
from app.services.knowledge import create_brand, create_knowledge, create_source


def main() -> None:
    open_pool()
    try:
        with transaction() as conn:
            create_brand(conn, "demo_brand", "示例品牌", "Asia/Shanghai")
            source = create_source(
                conn,
                {
                    "brand_code": "demo_brand",
                    "source_type": "brand_document",
                    "external_id": "tone-manual-2026",
                    "title": "2026品牌表达手册",
                    "text": "品牌表达应克制、具体，避免奇效和救世主式表达。",
                    "authority_level": 1,
                    "metadata": {"department": "品牌市场部"},
                },
            )
            result = create_knowledge(
                conn,
                {
                    "brand_code": "demo_brand",
                    "canonical_key": "tone.over_marketing.avoid_miracle_language",
                    "knowledge_type": "tone_rule",
                    "title": "避免奇效和救世主式表达",
                    "summary": "用具体、可观察的体验替代一夜回春等奇效表达。",
                    "content": "品牌表达应克制、具体。避免一夜回春、救命神器、修护天花板等强营销说法。",
                    "source_version_id": source["source_version"]["id"],
                    "authority_level": 1,
                    "confidence": 0.99,
                    "scope": {"channels": ["xiaohongshu"], "product_lines": ["skincare"]},
                    "attributes": {"dimension": "tone", "severity": "high"},
                    "chunks": [
                        {
                            "chunk_type": "rule",
                            "text": "品牌表达应克制、具体，避免奇效和救世主式表达。",
                            "search_terms": "品牌 调性 克制 奇效 救世主 过度营销",
                            "metadata": {},
                        },
                        {
                            "chunk_type": "negative_example",
                            "text": "一夜回春；熬夜党的救命神器；敏感肌修护天花板。",
                            "search_terms": "一夜回春 救命神器 修护天花板 反例",
                            "metadata": {},
                        },
                        {
                            "chunk_type": "positive_example",
                            "text": "连续使用一段时间后，皮肤状态看起来更稳定。",
                            "search_terms": "持续使用 稳定 可观察体验 正例",
                            "metadata": {},
                        },
                    ],
                },
            )
        print("示例数据已写入。请在 API 中审批知识版本：", result["version"]["id"])
    finally:
        close_pool()


if __name__ == "__main__":
    main()

