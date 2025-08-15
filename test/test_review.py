from unittest.mock import MagicMock

from src.review import (
    _hash,
    deduplicate_suggestions,
    detect_changed_ranges,
    post_comments,
    review_document,
)


def test_detect_changed_ranges():
    old = ["A", "B", "C"]
    new = ["A", "B changed", "C", "D"]
    ranges = detect_changed_ranges(old, new)
    assert ranges == [(1, 1), (3, 3)]


def test_deduplicate_suggestions():
    existing = set()
    items = [
        {"suggestion": "Fix typo", "quote": "teh"},
        {"suggestion": "Fix typo", "quote": "teh"},
        {"suggestion": "Capitalize", "quote": "word"},
    ]
    unique = deduplicate_suggestions(items, existing)
    assert len(unique) == 2
    assert all("hash" in item for item in unique)

    # Second run with same suggestion should yield no new items
    again = deduplicate_suggestions(
        [{"suggestion": "Fix typo", "quote": "teh"}], existing
    )
    assert again == []


def test_review_document_pipeline():
    drive = MagicMock()

    def files_get(fileId=None, fields=None):
        if fields == "appProperties, headRevisionId":
            return MagicMock(
                execute=MagicMock(
                    return_value={
                        "appProperties": {
                            "lastReviewedRevisionId": "1",
                            "suggestionHashes": "abcd",
                        },
                        "headRevisionId": "2",
                    }
                )
            )
        if fields == "description":
            return MagicMock(execute=MagicMock(return_value={"description": "share msg"}))
        return MagicMock(execute=MagicMock(return_value={}))

    drive.files.return_value.get.side_effect = files_get
    drive.revisions.return_value.get.return_value.execute.return_value = (
        "para1\npara2\n"
    )

    docs = MagicMock()
    docs.documents.return_value.get.return_value.execute.return_value = {
        "body": {
            "content": [
                {"paragraph": {"elements": [{"textRun": {"content": "para1"}}]}},
                {
                    "paragraph": {
                        "elements": [
                            {"textRun": {"content": "para2 updated"}}
                        ]
                    }
                },
            ]
        }
    }

    captured = {}

    def suggest(_text: str, context: str):
        captured["context"] = context
        return {"issue": "typo", "suggestion": "Fix typo", "severity": "major"}

    items = review_document(drive, docs, "doc1", suggest)
    assert len(items) == 1
    assert items[0]["suggestion"] == "Fix typo"
    assert captured["context"] == "share msg"
    assert items[0]["start_index"] == len("para1")
    assert items[0]["end_index"] == len("para1") + len("para2 updated")

    expected_hash = _hash("Fix typo", "para2 updated")
    update_body = drive.files.return_value.update.call_args.kwargs["body"]
    assert update_body["appProperties"]["lastReviewedRevisionId"] == "2"
    assert expected_hash in update_body["appProperties"]["suggestionHashes"]
    assert "abcd" in update_body["appProperties"]["suggestionHashes"]


def test_post_comments_calls_create(monkeypatch):
    create_calls = []
    reply_calls = []

    def fake_create(service, file_id, content, start_index=None, end_index=None):
        create_calls.append((file_id, content, start_index, end_index))
        return {"id": "c1"}

    def fake_reply(service, file_id, comment_id, content):
        reply_calls.append((file_id, comment_id, content))

    monkeypatch.setattr("src.review.create_comment", fake_create)
    monkeypatch.setattr("src.review.reply_to_comment", fake_reply)
    items = [
        {
            "suggestion": "Fix typo",
            "hash": "abcd",
            "quote": "teh",
            "start_index": 1,
            "end_index": 3,
        }
    ]
    post_comments("svc", "doc1", items)
    assert create_calls == [
        ("doc1", 'AI Reviewer: abcd\n"teh"\nFix typo', 1, 3)
    ]
    assert reply_calls == []


def test_post_comments_splits_long_comments(monkeypatch):
    create_calls = []
    reply_calls = []

    def fake_create(service, file_id, content, start_index=None, end_index=None):
        create_calls.append((file_id, content, start_index, end_index))
        return {"id": "c1"}

    def fake_reply(service, file_id, comment_id, content):
        reply_calls.append((file_id, comment_id, content))

    monkeypatch.setattr("src.review.create_comment", fake_create)
    monkeypatch.setattr("src.review.reply_to_comment", fake_reply)

    long_text = "a" * 5000
    items = [
        {
            "suggestion": long_text,
            "hash": "h",
            "quote": "snippet",
            "start_index": 0,
            "end_index": 1,
        }
    ]
    post_comments("svc", "doc1", items)

    # First chunk is posted as the main comment, remaining as replies
    assert len(create_calls) == 1
    assert len(reply_calls) == 1
    # Ensure the created comment respects size limit
    assert len(create_calls[0][1].encode("utf-8")) <= 4096
    assert len(reply_calls[0][2].encode("utf-8")) <= 4096
