"""小红书文章标准化与结构切分测试。"""

from app.services.article_chunking import build_article_chunks, normalize_article


def test_article_normalization_preserves_emoji_and_deduplicates_hashtags():
    title, body, hashtags = normalize_article(
        "  换季护肤记录🌿  ",
        "第一段。\r\n\r\n\r\n第二段。",
        ["#护肤分享", "护肤分享", "＃换季护肤"],
    )
    assert title == "换季护肤记录🌿"
    assert body == "第一段。\n\n第二段。"
    assert hashtags == ["护肤分享", "换季护肤"]


def test_article_chunks_include_original_and_enriched_text():
    chunks = build_article_chunks(
        "最近把护肤步骤做了减法",
        "换季时皮肤容易紧绷。\n\n我开始使用精华A。\n\n连续使用后状态更稳定。",
        ["护肤分享"],
        {
            "brand_name": "示例品牌",
            "article_type": "creator_submission",
            "product_code": "serum_a",
            "creator_type": "lifestyle",
            "content_type": "recommendation",
            "version_type": "creator_original",
        },
    )
    types = [chunk["chunk_type"] for chunk in chunks]
    assert "article_full" in types
    assert "article_title" in types
    assert "article_opening" in types
    assert "article_closing" in types
    assert "article_hashtags" in types
    opening = next(chunk for chunk in chunks if chunk["chunk_type"] == "article_opening")
    assert opening["original_text"] == "换季时皮肤容易紧绷。"
    assert "品牌：示例品牌" in opening["embedding_text"]
    assert "产品：serum_a" in opening["embedding_text"]

