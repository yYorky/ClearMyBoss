from unittest.mock import MagicMock

from src.google_docs import get_document_paragraphs, chunk_paragraphs


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
    assert chunks == ["a" * 10 + "b" * 10, "c" * 10]
