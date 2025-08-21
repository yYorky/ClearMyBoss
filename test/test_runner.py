from datetime import datetime
from unittest.mock import MagicMock

from src.main import run_once, _process_document, _latest_timestamp
import src.main as runner


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
    monkeypatch.setattr("src.main.review_comment_replies", lambda *_args: None)

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


def test_main_processes_pre_shared_docs(monkeypatch):
    drive = MagicMock()
    drive.changes.return_value.getStartPageToken.return_value.execute.return_value = {
        "startPageToken": "t0"
    }
    docs = MagicMock()
    monkeypatch.setattr(runner, "build_drive_service", lambda: drive)
    monkeypatch.setattr(runner, "build_docs_service", lambda: docs)
    monkeypatch.setattr(runner, "list_all_shared_docs", lambda svc: [{"id": "1"}, {"id": "2"}])

    processed: list[str] = []

    def fake_process(drive_service, docs_service, file):
        processed.append(file["id"])
        return True

    monkeypatch.setattr(runner, "_process_document", fake_process)
    monkeypatch.setattr(runner, "run_once", lambda d, ds, s, t: (s, t))

    import types, sys

    class FakeEvery:
        @property
        def minutes(self):
            return self

        def do(self, func):
            self.func = func
            return self

    class FakeSchedule(types.SimpleNamespace):
        def every(self, *args, **kwargs):
            return FakeEvery()

        def run_pending(self):
            raise KeyboardInterrupt()

    fake_schedule = FakeSchedule()
    monkeypatch.setitem(sys.modules, "schedule", fake_schedule)
    monkeypatch.setattr(runner.time, "sleep", lambda _x: None)

    runner.main()

    assert processed == ["1", "2"]
