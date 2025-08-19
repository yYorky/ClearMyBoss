"""Google Docs API utilities."""
from __future__ import annotations

from typing import Any

from .google_service import build_service

SCOPES = ["https://www.googleapis.com/auth/documents.readonly"]


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
