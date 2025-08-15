"""Google Docs API utilities."""
from __future__ import annotations

from typing import List, Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import settings

SCOPES = ["https://www.googleapis.com/auth/documents.readonly"]


def build_docs_service() -> Any:
    creds = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES
    )
    service = build("docs", "v1", credentials=creds)
    return service


def get_document_paragraphs(service: Any, document_id: str) -> List[str]:
    """Fetch a document and return its paragraphs as a list of strings."""
    doc = service.documents().get(documentId=document_id).execute()
    paragraphs: List[str] = []
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


def chunk_paragraphs(paragraphs: List[str], max_chars: int) -> List[str]:
    """Chunk paragraphs into groups limited by ``max_chars`` characters.

    Paragraphs are concatenated using newline characters so that the returned
    chunks mirror the exact text found in the document. ``max_chars`` therefore
    includes these newline separators when computing the size of each chunk.
    """

    chunks: List[str] = []
    current: List[str] = []
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
