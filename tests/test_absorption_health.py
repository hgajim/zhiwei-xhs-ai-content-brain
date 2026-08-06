from app.services.absorption_health import _diminishing_factor, _session_quality, _specific_feedback


def test_feedback_specificity_rejects_empty_and_limits_generic_words():
    assert _specific_feedback("") == 0
    assert _specific_feedback("很好") == 4
    assert _specific_feedback("标题先给出具体冲突，再用真实使用过程解释产品差异") > 10


def test_same_mode_material_has_diminishing_returns():
    assert _diminishing_factor(5) == 1.0
    assert _diminishing_factor(6) == 0.7
    assert _diminishing_factor(11) == 0.4
    assert _diminishing_factor(21) == 0.2


def test_revision_pair_requires_complete_before_and_after_material():
    complete = {
        "learning_mode": "revision_pair",
        "user_feedback": "删掉绝对功效，改成个人使用感受并限定适用人群",
        "original_title": "原稿标题",
        "original_body": "原稿正文" * 20,
        "revised_title": "终稿标题",
        "revised_body": "终稿正文" * 20,
    }
    incomplete = {**complete, "revised_title": "", "revised_body": ""}
    assert _session_quality(complete, []) > _session_quality(incomplete, [])
