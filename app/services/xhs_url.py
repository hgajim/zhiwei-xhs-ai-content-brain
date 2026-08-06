"""从公开小红书笔记 URL 解析标准 Article 结构化数据。"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class _JsonLdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_json_ld = False
        self.buffer: list[str] = []
        self.documents: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag.lower() == "script" and values.get("type", "").lower() == "application/ld+json":
            self.in_json_ld = True
            self.buffer = []

    def handle_data(self, data: str) -> None:
        if self.in_json_ld:
            self.buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "script" or not self.in_json_ld:
            return
        self.in_json_ld = False
        try:
            value = json.loads("".join(self.buffer))
            values = value if isinstance(value, list) else [value]
            self.documents.extend(x for x in values if isinstance(x, dict))
        except json.JSONDecodeError:
            pass


def parse_xhs_url(url: str) -> dict[str, Any]:
    """解析公开笔记；不绕过登录、验证码或访问控制。"""
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or parsed.hostname not in {"www.xiaohongshu.com", "xiaohongshu.com"}:
        raise ValueError("请输入有效的 https://www.xiaohongshu.com 笔记链接。")
    note_match = re.search(r"/(?:explore|discovery/item)/([0-9a-fA-F]{16,32})", parsed.path)
    if not note_match:
        raise ValueError("链接中没有识别到小红书笔记ID。")

    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    try:
        with urlopen(request, timeout=25) as response:
            html = response.read(3_000_000).decode("utf-8", errors="replace")
    except Exception as exc:
        raise ValueError(f"暂时无法访问该笔记：{exc}") from exc

    parser = _JsonLdParser()
    parser.feed(html)
    document = next(
        (x for x in parser.documents if x.get("@type") in {"Article", "VideoObject"}),
        None,
    )
    if not document:
        available_types = [str(x.get("@type")) for x in parser.documents if x.get("@type")]
        if available_types:
            raise ValueError(f"页面内容类型暂不支持：{', '.join(available_types)}。")
        raise ValueError("该页面没有公开结构化数据，可能需要登录、链接已过期或笔记不可见。")

    is_video = document.get("@type") == "VideoObject"
    body = str(document.get("description") or "").strip()
    headline = str(document.get("headline") or document.get("name") or "").strip()
    title = re.sub(r"\s*-\s*小红书\s*$", "", headline).strip()
    images = document.get("thumbnailUrl") if is_video else document.get("image")
    images = images or []
    if isinstance(images, str):
        images = [images]
    image_urls = [re.sub(r"^http://", "https://", str(x)) for x in images if x]
    hashtags = list(dict.fromkeys(re.findall(r"#([^#\s]+)", body)))
    author = document.get("author") if isinstance(document.get("author"), dict) else {}
    raw_stats = document.get("interactionStatistic") or []
    raw_stats = [raw_stats] if isinstance(raw_stats, dict) else raw_stats
    interaction = {}
    for stat in raw_stats if isinstance(raw_stats, list) else []:
        if not isinstance(stat, dict): continue
        kind = str(stat.get("interactionType", {}).get("@type", "") if isinstance(stat.get("interactionType"), dict) else stat.get("interactionType", "")).lower()
        value = stat.get("userInteractionCount")
        if "like" in kind or (not kind and len(raw_stats) == 1): interaction["like_count"] = value
        elif "comment" in kind: interaction["comment_count"] = value
        elif "share" in kind: interaction["share_count"] = value
        elif "bookmark" in kind or "collect" in kind: interaction["collect_count"] = value
    canonical = document.get("mainEntityOfPage") if isinstance(document.get("mainEntityOfPage"), dict) else {}
    return {
        "platform_note_id": note_match.group(1),
        "canonical_url": canonical.get("@id") or f"https://www.xiaohongshu.com/explore/{note_match.group(1)}",
        "title": title,
        "body": body,
        "hashtags": hashtags,
        "creator_name": author.get("name"),
        "published_at": document.get("datePublished") or document.get("uploadDate"),
        "modified_at": document.get("dateModified"),
        "image_urls": image_urls,
        "image_count": len(image_urls),
        "like_count": interaction.get("like_count"),
        "collect_count": interaction.get("collect_count"),
        "comment_count": interaction.get("comment_count"),
        "share_count": interaction.get("share_count"),
        "media_type": "video" if is_video else "article",
        "video_url": document.get("contentUrl") if is_video else None,
        "video_duration": document.get("duration") if is_video else None,
        "source": "public_json_ld_video" if is_video else "public_json_ld",
    }
