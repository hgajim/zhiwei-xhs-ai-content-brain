from app.services.learning import learning_input_hash


def test_learning_input_hash_is_stable_and_normalizes_whitespace():
    first = learning_input_hash("positive_example", "article-a", None, " 开头好   很自然 ")
    second = learning_input_hash("positive_example", "article-a", None, "开头好 很自然")
    assert first == second


def test_learning_input_hash_keeps_meaningful_differences():
    base = learning_input_hash("positive_example", "article-a", None, "开头好")
    assert base != learning_input_hash("negative_example", "article-a", None, "开头好")
    assert base != learning_input_hash("positive_example", "article-b", None, "开头好")
    assert base != learning_input_hash("positive_example", "article-a", None, "标题好")
