from datetime import datetime
from unittest.mock import MagicMock

from src.main import run_once


def test_run_once_reviews_and_posts(monkeypatch):
    drive = MagicMock()
    docs = MagicMock()

    monkeypatch.setattr(
        "src.main.list_recent_docs", lambda svc, since: [{"id": "1"}, {"id": "2"}]
    )

    reviews = [
        [{"suggestion": "s1", "hash": "h1", "start_index": 0, "end_index": 1}],
        [],
    ]

    def fake_review(drive_service, docs_service, doc_id, suggest_fn):
        return reviews.pop(0)

    monkeypatch.setattr("src.main.review_document", fake_review)

    posted = []

    def fake_post(drive_service, doc_id, items):
        posted.append((doc_id, items))

    monkeypatch.setattr("src.main.post_comments", fake_post)

    since = datetime.utcnow()
    new_since = run_once(drive, docs, since)

    assert posted == [(
        "1",
        [{"suggestion": "s1", "hash": "h1", "start_index": 0, "end_index": 1}],
    )]
    assert isinstance(new_since, datetime) and new_since >= since
