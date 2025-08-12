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
    """Chunk paragraphs into groups limited by ``max_chars`` characters."""
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    for para in paragraphs:
        if current_len + len(para) > max_chars and current:
            chunks.append("".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += len(para)
    if current:
        chunks.append("".join(current))
    return chunks
