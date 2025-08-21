from datetime import datetime
from unittest.mock import MagicMock

from src.main import run_once, _process_document, _latest_timestamp


def test_run_once_reviews_and_posts(monkeypatch):
    drive = MagicMock()
    docs = MagicMock()
    monkeypatch.setattr(
        "src.main.list_recent_docs",
        lambda svc, since, token: ([{"id": "1"}, {"id": "2"}], token),
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
    new_since, new_token = run_once(drive, docs, since, "t0")

    assert posted == [(
        "1",
        [{"suggestion": "s1", "hash": "h1", "start_index": 0, "end_index": 1}],
    )]
    assert isinstance(new_since, datetime) and new_since >= since
    assert new_token == "t0"


def test_process_document_success(monkeypatch):
    drive = MagicMock()
    docs = MagicMock()
    file = {"id": "1", "name": "Doc"}

    monkeypatch.setattr(
        "src.main.review_document",
        lambda drive_service, docs_service, doc_id, suggest_fn: [
            {"suggestion": "s1"}
        ],
    )

    posted: list[tuple[str, list[dict[str, str]]]] = []

    def fake_post(drive_service, doc_id, items):
        posted.append((doc_id, items))

    monkeypatch.setattr("src.main.post_comments", fake_post)

    assert _process_document(drive, docs, file) is True
    assert posted == [("1", [{"suggestion": "s1"}])]


def test_process_document_handles_errors(monkeypatch):
    drive = MagicMock()
    docs = MagicMock()
    file = {"id": "1"}

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("src.main.review_document", boom)

    assert _process_document(drive, docs, file) is False


def test_latest_timestamp():
    since = datetime(2020, 1, 1)
    file = {
        "modifiedTime": "2021-02-01T00:00:00Z",
        "sharedWithMeTime": "2022-06-01T00:00:00Z",
    }

    assert _latest_timestamp(file, since) == datetime(2022, 6, 1)
