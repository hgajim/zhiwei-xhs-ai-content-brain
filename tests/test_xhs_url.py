"""小红书公开结构化数据解析测试。"""

from app.services.xhs_url import _JsonLdParser, parse_xhs_url


def test_json_ld_article_parser():
    parser = _JsonLdParser()
    parser.feed('''<script type="application/ld+json">{"@type":"Article","headline":"标题 - 小红书"}</script>''')
    assert parser.documents[0]["headline"] == "标题 - 小红书"


def test_invalid_json_ld_is_ignored():
    parser = _JsonLdParser()
    parser.feed('<script type="application/ld+json">not-json</script>')
    assert parser.documents == []


def test_json_ld_video_parser(monkeypatch):
    html = '''<script type="application/ld+json">{
      "@context":"https://schema.org","@type":"VideoObject",
      "name":"气垫实测 - 小红书","description":"实测正文 #底妆",
      "thumbnailUrl":"http://img.example/cover.jpg",
      "uploadDate":"2026-08-05T09:51:13Z",
      "contentUrl":"https://video.example/test.mp4","duration":"00:41",
      "interactionStatistic":{"userInteractionCount":243}
    }</script>'''.encode("utf-8")

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self, _: int): return html

    monkeypatch.setattr("app.services.xhs_url.urlopen", lambda *args, **kwargs: Response())
    result = parse_xhs_url("https://www.xiaohongshu.com/explore/6a70459c000000003300bc68")
    assert result["title"] == "气垫实测"
    assert result["media_type"] == "video"
    assert result["image_urls"] == ["https://img.example/cover.jpg"]
    assert result["video_duration"] == "00:41"
    assert result["like_count"] == 243
