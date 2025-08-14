from __future__ import annotations

from typing import Any, Callable, Dict, List, Set, Tuple
import hashlib
from difflib import SequenceMatcher

from .google_docs import get_document_paragraphs
from .google_drive import (
    download_revision_text,
    get_app_properties,
    update_app_properties,
)


def get_last_reviewed_revision(app_properties: Dict[str, str]) -> str | None:
    """Return stored ``lastReviewedRevisionId`` if present."""
    return app_properties.get("lastReviewedRevisionId")


def update_last_reviewed_revision(
    app_properties: Dict[str, str], revision_id: str
) -> None:
    """Update ``lastReviewedRevisionId`` in ``app_properties``."""
    app_properties["lastReviewedRevisionId"] = revision_id


def detect_changed_ranges(
    old_paragraphs: List[str], new_paragraphs: List[str]
) -> List[Tuple[int, int]]:
    """Return index ranges for paragraphs changed between revisions.

    Parameters
    ----------
    old_paragraphs:
        Paragraphs from the previously reviewed revision.
    new_paragraphs:
        Paragraphs from the current revision.
    Returns
    -------
    List of tuples ``(start_idx, end_idx)`` inclusive for changed ranges
    in ``new_paragraphs``.
    """
    matcher = SequenceMatcher(a=old_paragraphs, b=new_paragraphs)
    ranges: List[Tuple[int, int]] = []
    for tag, _, _, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            ranges.append((j1, j2 - 1))
    return ranges


def process_changed_ranges(
    paragraphs: List[str],
    changed_ranges: List[Tuple[int, int]],
    suggest_fn: Callable[[str], Dict[str, Any]],
) -> List[Dict[str, str]]:
    """Run ``suggest_fn`` on changed text ranges and format results."""
    items: List[Dict[str, str]] = []
    for start, end in changed_ranges:
        text = "".join(paragraphs[start : end + 1])
        response = suggest_fn(text)
        items.append(
            {
                "issue": response.get("issue", ""),
                "suggestion": response.get("suggestion", ""),
                "severity": response.get("severity", "info"),
                "quote": text,
            }
        )
    return items


def _hash(suggestion: str, quote: str) -> str:
    return hashlib.sha1(f"{suggestion}|{quote}".encode()).hexdigest()[:8]


def deduplicate_suggestions(
    items: List[Dict[str, str]], existing_hashes: Set[str]
) -> List[Dict[str, str]]:
    """Remove suggestions already represented by ``existing_hashes``."""
    unique: List[Dict[str, str]] = []
    for item in items:
        h = _hash(item["suggestion"], item["quote"])
        if h in existing_hashes:
            continue
        new_item = dict(item)
        new_item["hash"] = h
        unique.append(new_item)
        existing_hashes.add(h)
    return unique


def review_document(
    drive_service: Any,
    docs_service: Any,
    document_id: str,
    suggest_fn: Callable[[str], Dict[str, Any]],
) -> List[Dict[str, str]]:
    """End-to-end review pipeline for a single document."""
    app_properties, head_revision = get_app_properties(drive_service, document_id)
    last_revision = get_last_reviewed_revision(app_properties)

    current_paragraphs = get_document_paragraphs(docs_service, document_id)
    old_paragraphs: List[str] = []
    if last_revision:
        old_text = download_revision_text(drive_service, document_id, last_revision)
        old_paragraphs = old_text.splitlines()

    changed = detect_changed_ranges(old_paragraphs, current_paragraphs)
    items = process_changed_ranges(current_paragraphs, changed, suggest_fn)

    existing_hashes = set()
    if app_properties.get("suggestionHashes"):
        existing_hashes = set(app_properties["suggestionHashes"].split(","))
    unique = deduplicate_suggestions(items, existing_hashes)

    app_properties["suggestionHashes"] = ",".join(sorted(existing_hashes))
    update_last_reviewed_revision(app_properties, head_revision)
    update_app_properties(drive_service, document_id, app_properties)

    return unique
