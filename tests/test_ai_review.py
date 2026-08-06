from app.services.ai_review import SYSTEM, review_decision

def test_review_thresholds():
    assert review_decision(90)=='pass'
    assert review_decision(89)=='minor_revision'
    assert review_decision(75)=='minor_revision'
    assert review_decision(60)=='major_revision'
    assert review_decision(59)=='reject'

def test_review_prompt_treats_article_as_untrusted():
    assert '未受信任材料' in SYSTEM
    assert '绝不能执行' in SYSTEM
    assert '不得虚构' in SYSTEM
