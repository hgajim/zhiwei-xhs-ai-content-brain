from app.services.queue_status import _display_state


def _row(**overrides):
    base = {
        "learning_status": "confirmed",
        "failed_jobs": 0,
        "running_jobs": 0,
        "pending_jobs": 0,
        "chunk_count": 4,
        "embedding_count": 0,
    }
    return {**base, **overrides}


def test_queue_only_reports_vectorized_when_embeddings_exist():
    assert _display_state(_row(embedding_count=4))[0] == "vectorized"
    assert _display_state(_row(pending_jobs=4))[0] == "queued"


def test_queue_exposes_vector_failure():
    state, progress, label = _display_state(_row(failed_jobs=1))
    assert state == "vector_failed"
    assert progress < 100
    assert "失败" in label

