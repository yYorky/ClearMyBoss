from unittest.mock import MagicMock
from typing import Any

from src.review import (
    _hash,
    _prune_hashes,
    split_into_byte_chunks,
    deduplicate_suggestions,
    detect_changed_ranges,
    process_changed_ranges,
    post_comments,
    review_document,
    review_comment_replies,
    SUGGESTION_HASHES_KEY,
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


def test_deduplicate_suggestions_skips_empty():
    existing = set()
    items = [
        {"suggestion": "", "quote": "teh"},
        {"suggestion": "Fix typo", "quote": "teh"},
    ]
    unique = deduplicate_suggestions(items, existing)
    assert len(unique) == 1
    assert unique[0]["suggestion"] == "Fix typo"
    # existing should only contain hash for non-empty suggestion
    assert len(existing) == 1


def test_prune_hashes_limit():
    hashes = [f"{i:08x}" for i in range(30)]
    result = _prune_hashes(hashes)
    assert len(result.encode("utf-8")) <= 124


def test_process_changed_ranges_chunks_long_range():
    paragraphs = ["p0", "a" * 600, "b" * 600, "p3"]
    changed = [(1, 2)]
    captured: list[str] = []

    def suggest(text: str, _context: str) -> dict:
        captured.append(text)
        return {"issue": "", "suggestion": text, "severity": "info"}

    items = process_changed_ranges(paragraphs, changed, suggest)
    assert len(items) == 2
    assert captured == ["a" * 600, "b" * 600]
    start = len("p0") + 1
    assert items[0]["start_index"] == start
    assert items[0]["end_index"] == start + 600
    assert items[1]["start_index"] == start + 601
    assert items[1]["end_index"] == start + 1201


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
    assert items[0]["start_index"] == len("para1") + 1
    assert items[0]["end_index"] == len("para1") + 1 + len("para2 updated")

    expected_hash = _hash("Fix typo", "para2 updated")
    update_body = drive.files.return_value.update.call_args.kwargs["body"]
    assert update_body["appProperties"]["lastReviewedRevisionId"] == "2"
    assert expected_hash in update_body["appProperties"]["suggestionHashes"]
    assert "abcd" in update_body["appProperties"]["suggestionHashes"]


def test_review_document_ignores_empty_suggestions():
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

    def suggest(_text: str, _context: str):
        return {"issue": "typo", "suggestion": "", "severity": "major"}

    items = review_document(drive, docs, "doc1", suggest)
    assert items == []
    update_body = drive.files.return_value.update.call_args.kwargs["body"]
    # suggestionHashes should remain unchanged
    assert update_body["appProperties"]["suggestionHashes"] == "abcd"


def test_post_comments_calls_create(monkeypatch):
    create_calls = []
    reply_calls = []

    def fake_create(service, file_id, content, revision_id="head", regions=None):
        create_calls.append((file_id, content, revision_id, regions))
        return {"id": "c1"}

    def fake_reply(service, file_id, comment_id, content):
        reply_calls.append((file_id, comment_id, content))

    monkeypatch.setattr("src.review.create_comment", fake_create)
    monkeypatch.setattr("src.review.reply_to_comment", fake_reply)
    monkeypatch.setattr(
        "src.review.download_revision_text", lambda *_args, **_kwargs: "abc\n"
    )
    items = [
        {
            "suggestion": "Fix typo",
            "hash": "abcd",
            "quote": "teh",
            "start_index": 1,
            "end_index": 3,
        }
    ]
    post_comments("drive", "doc1", items)
    expected_region = {"segment": {"startIndex": 1, "endIndex": 3}}
    assert create_calls == [("doc1", "Fix typo", "head", [expected_region])]
    assert reply_calls == []


def test_post_comments_splits_long_comments(monkeypatch, region):
    create_calls = []
    reply_calls = []

    def fake_create(service, file_id, content, revision_id="head", regions=None):
        create_calls.append((file_id, content, revision_id, regions))
        return {"id": "c1"}

    def fake_reply(service, file_id, comment_id, content):
        reply_calls.append((file_id, comment_id, content))

    monkeypatch.setattr("src.review.create_comment", fake_create)
    monkeypatch.setattr("src.review.reply_to_comment", fake_reply)
    monkeypatch.setattr(
        "src.review.download_revision_text", lambda *_args, **_kwargs: "abc\n"
    )

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
    post_comments("drive", "doc1", items)

    # First chunk is posted as the main comment, remaining as replies
    assert len(create_calls) == 1
    assert len(reply_calls) == 1
    # Ensure the created comment respects size limit
    assert len(create_calls[0][1].encode("utf-8")) <= 4096
    assert len(reply_calls[0][2].encode("utf-8")) <= 4096
    assert create_calls[0][3] == [region]


def test_suggestion_hashes_property_total_size_limit():
    drive = MagicMock()

    existing_hashes = [f"{i:08x}" for i in range(12)]
    suggestion_hashes = ",".join(existing_hashes)

    def files_get(fileId=None, fields=None):
        if fields == "appProperties, headRevisionId":
            return MagicMock(
                execute=MagicMock(
                    return_value={
                        "appProperties": {"suggestionHashes": suggestion_hashes},
                        "headRevisionId": "2",
                    }
                )
            )
        if fields == "description":
            return MagicMock(execute=MagicMock(return_value={"description": ""}))
        return MagicMock(execute=MagicMock(return_value={}))

    drive.files.return_value.get.side_effect = files_get

    docs = MagicMock()
    docs.documents.return_value.get.return_value.execute.return_value = {
        "body": {
            "content": [
                {"paragraph": {"elements": [{"textRun": {"content": "para1"}}]}},
                {"paragraph": {"elements": [{"textRun": {"content": "para2"}}]}},
            ]
        }
    }

    def suggest(_text: str, _context: str) -> dict:
        return {"issue": "", "suggestion": "Fix typo", "severity": "info"}

    review_document(drive, docs, "doc1", suggest)
    update_body = drive.files.return_value.update.call_args.kwargs["body"]
    value = update_body["appProperties"][SUGGESTION_HASHES_KEY]
    total = len(SUGGESTION_HASHES_KEY.encode("utf-8")) + len(value.encode("utf-8"))
    assert total <= 124


def test_split_into_byte_chunks_utf8_boundary():
    text = "😀" * 2000
    max_bytes = 4096
    chunks = split_into_byte_chunks(text, max_bytes)
    assert all(len(chunk.encode("utf-8")) <= max_bytes for chunk in chunks)
    assert "".join(chunks) == text


def test_review_comment_replies(monkeypatch):
    drive = MagicMock()
    drive.about.return_value.get.return_value.execute.return_value = {
        "user": {"displayName": "Bot"}
    }

    def fake_list_comments(service, file_id):
        return [
            {"id": "c1", "author": {"displayName": "Bot"}, "content": "orig"},
            {"id": "c2", "author": {"displayName": "User"}},
        ]

    def fake_list_replies(service, file_id, comment_id):
        if comment_id == "c1":
            return [
                {"id": "r0", "author": {"displayName": "Bot"}, "content": "old"},
                {"id": "r1", "author": {"displayName": "User"}, "content": "bad"},
            ]
        return []

    reply_calls: list[tuple[str, str, str]] = []

    def fake_reply(service, file_id, comment_id, content):
        reply_calls.append((file_id, comment_id, content))

    update_calls: list[tuple[str, str]] = []

    def fake_update(fileId=None, commentId=None, body=None, fields=None):
        update_calls.append((fileId, commentId))

        class Exec:
            def execute(self, num_retries=3):
                return {"id": commentId}

        return Exec()

    drive.comments.return_value.update.side_effect = fake_update

    monkeypatch.setattr("src.review.list_comments", fake_list_comments)
    monkeypatch.setattr("src.review.list_replies", fake_list_replies)
    monkeypatch.setattr("src.review.reply_to_comment", fake_reply)

    reviewed: list[tuple[str, str]] = []

    def review_fn(text: str, context: str) -> dict[str, Any]:
        reviewed.append((text, context))
        return {"reply": "guidance", "resolve": True}

    review_comment_replies(drive, "doc1", review_fn)

    assert reviewed == [("bad", "orig")]
    assert reply_calls == [("doc1", "c1", "guidance")]
    assert update_calls == [("doc1", "c1")]
