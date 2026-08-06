"""知识切分的基础回归测试。"""

import unittest

from app.services.chunking import normalize_text, segment_for_search, semantic_chunks


class ChunkingTests(unittest.TestCase):
    def test_normalize_text(self):
        self.assertEqual(normalize_text("第一行\r\n\r\n\r\n第二行"), "第一行\n\n第二行")

    def test_markdown_sections_are_preserved(self):
        text = "# 原则\n表达要克制。\n\n## 反例\n一夜回春。\n\n## 正例\n状态看起来更稳定。"
        chunks = semantic_chunks(text, max_chars=30)
        self.assertGreaterEqual(len(chunks), 3)
        self.assertTrue(any("反例" in chunk for chunk in chunks))

    def test_empty_text(self):
        self.assertEqual(semantic_chunks("   \n"), [])

    def test_basic_chinese_search_segmentation(self):
        terms = segment_for_search("熬夜救命神器 serumA")
        self.assertIn("熬夜", terms)
        self.assertIn("救命", terms)
        self.assertIn("seruma", terms)


if __name__ == "__main__":
    unittest.main()
