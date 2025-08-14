"""Scheduled runner entry point for ClearMyBoss."""
from __future__ import annotations

from datetime import datetime
import time
from typing import Any

from .google_drive import build_drive_service, list_recent_docs
from .google_docs import build_docs_service
from .groq_client import get_suggestions
from .review import review_document, post_comments


def groq_suggest(text: str, context: str) -> dict[str, str]:
    """Wrapper around :func:`get_suggestions` producing review item dicts."""
    prompt = f"{context}\n\n{text}" if context else text
    resp = get_suggestions(prompt)
    suggestion = ""
    if resp.get("choices"):
        choice = resp["choices"][0]
        suggestion = choice.get("text") or choice.get("message", {}).get("content", "")
    return {"issue": "", "suggestion": suggestion.strip(), "severity": "info"}


def run_once(drive_service: Any, docs_service: Any, since: datetime) -> datetime:
    """Process documents modified since ``since`` and return new timestamp."""
    files = list_recent_docs(drive_service, since)
    for f in files:
        doc_id = f["id"]
        items = review_document(drive_service, docs_service, doc_id, groq_suggest)
        if items:
            post_comments(drive_service, doc_id, items)
    return datetime.utcnow()


def main() -> None:
    drive_service = build_drive_service()
    docs_service = build_docs_service()
    since = datetime.utcnow()
    import schedule

    def job() -> None:
        nonlocal since
        since = run_once(drive_service, docs_service, since)

    schedule.every(5).minutes.do(job)
    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":  # pragma: no cover
    main()
