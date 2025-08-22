"""Google Docs API utilities."""
from __future__ import annotations

from typing import Any

from .google_service import build_service

# Full Docs scope is required for creating named ranges and inserting markers.
SCOPES = ["https://www.googleapis.com/auth/documents"]


def build_docs_service() -> Any:
    return build_service("docs", "v1", SCOPES)


def get_document_paragraphs(service: Any, document_id: str) -> list[str]:
    """Fetch a document and return its paragraphs as a list of strings."""
    doc = service.documents().get(documentId=document_id).execute()
    paragraphs: list[str] = []
    for element in doc.get("body", {}).get("content", []):
        para = element.get("paragraph")
        if not para:
            continue
        texts = [
            el.get("textRun", {}).get("content", "")
            for el in para.get("elements", [])
            if "textRun" in el
        ]
        if texts:
            paragraphs.append("".join(texts))
    return paragraphs


def chunk_paragraphs(paragraphs: list[str], max_chars: int) -> list[str]:
    """Chunk paragraphs into groups limited by ``max_chars`` characters.

    Paragraphs are concatenated using newline characters so that the returned
    chunks mirror the exact text found in the document. ``max_chars`` therefore
    includes these newline separators when computing the size of each chunk.
    """

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        # ``para_len`` accounts for a preceding newline when ``current`` already
        # contains content so that the length matches the document text.
        para_len = len(para) + (1 if current else 0)
        if current_len + para_len > max_chars and current:
            chunks.append("\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += para_len
    if current:
        chunks.append("\n".join(current))
    return chunks


def create_named_range(
    service: Any,
    document_id: str,
    name: str,
    start_index: int,
    end_index: int,
    link_marker: bool = True,
) -> str:
    """Create a named range and optionally insert a linked "🔗" marker.

    Parameters
    ----------
    service: Any
        Authenticated Docs API service.
    document_id: str
        ID of the document to update.
    name: str
        Human-friendly label for the range.
    start_index, end_index: int
        Character offsets that define the range.
    link_marker: bool, optional
        When ``True`` (default) a "🔗" character linked to the range is
        inserted after ``end_index`` so readers can jump to the span.
    Returns
    -------
    str
        The ``namedRangeId`` assigned by the Docs API.
    """

    requests = [
        {
            "createNamedRange": {
                "name": name,
                "range": {"startIndex": start_index, "endIndex": end_index},
            }
        }
    ]
    result = (
        service.documents()
        .batchUpdate(documentId=document_id, body={"requests": requests})
        .execute(num_retries=3)
    )
    named_range_id = (
        result.get("replies", [{}])[0]
        .get("createNamedRange", {})
        .get("namedRangeId", "")
    )

    if link_marker and named_range_id:
        marker = "🔗"
        # Emoji use two UTF-16 code units in Docs indexes
        marker_len = 2
        marker_requests = [
            {"insertText": {"location": {"index": end_index}, "text": marker}},
            {
                "updateTextStyle": {
                    "range": {
                        "startIndex": end_index,
                        "endIndex": end_index + marker_len,
                    },
                    "textStyle": {"link": {"bookmarkId": named_range_id}},
                    "fields": "link",
                }
            },
        ]
        service.documents().batchUpdate(
            documentId=document_id, body={"requests": marker_requests}
        ).execute(num_retries=3)

    return named_range_id
