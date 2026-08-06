"""低操作教学层的确定性逻辑测试。"""

from app.services.learning import _normalize_classification, _normalize_insights, text_changes


def test_text_changes_extracts_replacement():
    changes = text_changes("标题\n用了立刻变白", "标题\n使用后看起来更透亮")
    assert changes == [{
        "operation": "替换",
        "before": "用了立刻变白",
        "after": "使用后看起来更透亮",
    }]


def test_low_confidence_always_needs_confirmation():
    insights = _normalize_insights({"insights": [{
        "dimension": "tone",
        "sentiment": "revision",
        "judgment": "语气被弱化",
        "rationale": "删除绝对化措辞",
        "reusable_rule": "体验表达避免绝对承诺",
        "confidence": 0.6,
        "needs_confirmation": False,
    }]})
    assert insights[0]["needs_confirmation"] is True


def test_unknown_taxonomy_is_safely_normalized():
    insights = _normalize_insights({"insights": [{
        "dimension": "unknown",
        "sentiment": "unknown",
        "judgment": "判断",
        "rationale": "理由",
        "reusable_rule": "规则",
        "confidence": 2,
    }]})
    assert insights[0]["dimension"] == "other"
    assert insights[0]["sentiment"] == "neutral"
    assert insights[0]["confidence"] == 1


def test_normalize_content_classification_limits_secondary_types():
    result = _normalize_classification({"content_classification": {
        "primary_type": "强种草笔记",
        "secondary_types": ["强种草笔记", "搜索承接笔记", "信任背书笔记", "大曝光笔记"],
        "target_audience": ["敏感肌用户"],
        "confidence": 88,
        "objective_score": 91,
        "rationale": "痛点、场景、利益点和实测证据完整",
    }})
    assert result is not None
    assert result["primary_type"] == "强种草笔记"
    assert result["secondary_types"] == ["搜索承接笔记", "信任背书笔记"]
    assert result["confidence"] == 88


def test_reject_unknown_content_classification():
    assert _normalize_classification({"content_classification": {"primary_type": "随便分类"}}) is None
