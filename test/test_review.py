from unittest.mock import MagicMock

from src.review import (
    _hash,
    deduplicate_suggestions,
    detect_changed_ranges,
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
    drive.files.return_value.get.return_value.execute.return_value = {
        "appProperties": {"lastReviewedRevisionId": "1", "suggestionHashes": "abcd"},
        "headRevisionId": "2",
    }
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

    def suggest(_text: str):
        return {"issue": "typo", "suggestion": "Fix typo", "severity": "major"}

    items = review_document(drive, docs, "doc1", suggest)
    assert len(items) == 1
    assert items[0]["suggestion"] == "Fix typo"

    expected_hash = _hash("Fix typo", "para2 updated")
    update_body = drive.files.return_value.update.call_args.kwargs["body"]
    assert update_body["appProperties"]["lastReviewedRevisionId"] == "2"
    assert expected_hash in update_body["appProperties"]["suggestionHashes"]
    assert "abcd" in update_body["appProperties"]["suggestionHashes"]
