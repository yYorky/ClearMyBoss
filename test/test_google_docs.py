from unittest.mock import MagicMock

from src.google_docs import (
    get_document_paragraphs,
    chunk_paragraphs,
    create_named_range,
)


def test_get_document_paragraphs():
    service = MagicMock()
    service.documents.return_value.get.return_value.execute.return_value = {
        "body": {
            "content": [
                {"paragraph": {"elements": [{"textRun": {"content": "Hello"}}]}},
                {"paragraph": {"elements": [{"textRun": {"content": "World"}}]}},
            ]
        }
    }
    paragraphs = get_document_paragraphs(service, "docid")
    assert paragraphs == ["Hello", "World"]


def test_chunk_paragraphs():
    paragraphs = ["a" * 10, "b" * 10, "c" * 10]
    chunks = chunk_paragraphs(paragraphs, max_chars=25)
    assert chunks == ["a" * 10 + "\n" + "b" * 10, "c" * 10]


def test_create_named_range_inserts_marker():
    service = MagicMock()
    service.documents.return_value.batchUpdate.return_value.execute.side_effect = [
        {"replies": [{"createNamedRange": {"namedRangeId": "nr1"}}]},
        {},
    ]
    range_id = create_named_range(service, "doc", "label", 1, 2)
    assert range_id == "nr1"
    batch_calls = service.documents.return_value.batchUpdate.call_args_list
    assert batch_calls[0].kwargs == {
        "documentId": "doc",
        "body": {
            "requests": [
                {
                    "createNamedRange": {
                        "name": "label",
                        "range": {"startIndex": 1, "endIndex": 2},
                    }
                }
            ]
        },
    }
    assert batch_calls[1].kwargs["documentId"] == "doc"
