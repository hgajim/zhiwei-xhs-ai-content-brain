"""知识内容切分。

这里采用结构感知切分：优先按 Markdown 标题和段落边界切分，
避免将一条规则或一个案例原因机械截断。
"""

from __future__ import annotations

import re


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def segment_for_search(text: str) -> str:
    """生成无需额外中文分词服务的基础检索词。

    中文连续文本生成单字和双字词，英文与数字保留原词。
    这不是专业分词器，但能保证第一版关键词检索可用；后续可无缝替换。
    """
    normalized = normalize_text(text).lower()
    terms: list[str] = []
    for token in re.findall(r"[\u4e00-\u9fff]+|[a-z0-9_]+", normalized):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            terms.extend(token)
            terms.extend(token[index : index + 2] for index in range(len(token) - 1))
        else:
            terms.append(token)
    # 去重但保留首次出现顺序，避免索引文本无意义膨胀。
    return " ".join(dict.fromkeys(terms))


def semantic_chunks(text: str, max_chars: int = 900) -> list[str]:
    """按标题和段落切分，并在超长时按句末标点继续拆分。"""
    normalized = normalize_text(text)
    if not normalized:
        return []

    blocks = re.split(r"\n(?=#{1,6}\s)|\n\s*\n", normalized)
    chunks: list[str] = []
    current = ""

    for block in (part.strip() for part in blocks if part.strip()):
        # Markdown 标题代表新的语义章节，原则、正例和反例不能互相合并。
        if block.startswith("#") and current:
            chunks.append(current)
            current = ""

        if len(block) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            sentences = re.split(r"(?<=[。！？；.!?;])\s*", block)
            piece = ""
            for sentence in (s.strip() for s in sentences if s.strip()):
                if piece and len(piece) + len(sentence) + 1 > max_chars:
                    chunks.append(piece)
                    piece = sentence
                else:
                    piece = f"{piece}\n{sentence}".strip()
            if piece:
                chunks.append(piece)
            continue

        if current and len(current) + len(block) + 2 > max_chars:
            chunks.append(current)
            current = block
        else:
            current = f"{current}\n\n{block}".strip()

    if current:
        chunks.append(current)
    return chunks
