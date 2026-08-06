"""Markdown TOML 头信息解析测试。"""

import tempfile
import unittest
from pathlib import Path

from app.services.markdown import parse_markdown


class MarkdownImportTests(unittest.TestCase):
    def test_parse_toml_frontmatter(self):
        content = """+++
canonical_key = "tone.test"
knowledge_type = "tone_rule"
title = "测试规则"
+++
# 原则

表达要具体。
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rule.md"
            path.write_text(content, encoding="utf-8")
            metadata, body = parse_markdown(path)
        self.assertEqual(metadata["canonical_key"], "tone.test")
        self.assertIn("表达要具体", body)


if __name__ == "__main__":
    unittest.main()
