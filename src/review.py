from __future__ import annotations

from typing import Any, Callable, Dict, List, Set, Tuple
import hashlib
import logging
from difflib import SequenceMatcher

from .google_docs import chunk_paragraphs, get_document_paragraphs
from .google_apps_script import create_comment
from .google_drive import (
    download_revision_text,
    get_app_properties,
    get_share_message,
    update_app_properties,
    reply_to_comment,
)


# Maximum allowed bytes for a single app property (key + value).
MAX_APP_PROPERTY_BYTES = 124

SUGGESTION_HASHES_KEY = "suggestionHashes"


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
    suggest_fn: Callable[[str, str], Dict[str, Any]],
    context: str = "",
    chunk_chars: int = 800,
) -> List[Dict[str, str]]:
    """Run ``suggest_fn`` on changed text ranges and format results.

    Each changed range is further divided into chunks using
    :func:`src.google_docs.chunk_paragraphs` so that large edits produce
    multiple concise comments.
    """
    # Pre-compute cumulative character offsets for each paragraph so we can
    # derive ``start_index``/``end_index`` for changed ranges.
    offsets: List[int] = [0]
    for para in paragraphs:
        # Account for the trailing newline that separates paragraphs in the
        # document's plain-text representation.
        offsets.append(offsets[-1] + len(para) + 1)

    items: List[Dict[str, str]] = []
    for start, end in changed_ranges:
        start_offset = offsets[start]
        para_slice = paragraphs[start : end + 1]
        chunks = chunk_paragraphs(para_slice, chunk_chars)
        relative = 0
        for i, chunk in enumerate(chunks):
            response = suggest_fn(chunk, context)
            chunk_start = start_offset + relative
            chunk_end = chunk_start + len(chunk)
            items.append(
                {
                    "issue": response.get("issue", ""),
                    "suggestion": response.get("suggestion", ""),
                    "severity": response.get("severity", "info"),
                    "quote": chunk,
                    "start_index": chunk_start,
                    "end_index": chunk_end,
                }
            )
            relative += len(chunk)
            # ``chunks`` are joined with newlines in the document; account for
            # the separator except after the last chunk.
            if i < len(chunks) - 1:
                relative += 1
    return items


def _hash(suggestion: str, quote: str) -> str:
    return hashlib.sha1(f"{suggestion}|{quote}".encode()).hexdigest()[:8]


def _prune_hashes(hashes: List[str], max_bytes: int = 124) -> str:
    """Join ``hashes`` ensuring result is <= ``max_bytes`` bytes.

    Oldest hashes (at the start of ``hashes``) are dropped first if the
    combined comma-separated string would exceed ``max_bytes`` bytes. A warning
    is logged when pruning occurs.
    """

    joined = ",".join(hashes)
    if len(joined.encode("utf-8")) <= max_bytes:
        return joined

    pruned = False
    while hashes and len(joined.encode("utf-8")) > max_bytes:
        hashes.pop(0)
        joined = ",".join(hashes)
        pruned = True

    if pruned:
        logging.warning(
            "Pruned suggestion hashes to fit within %d bytes", max_bytes
        )

    return joined


def deduplicate_suggestions(
    items: List[Dict[str, str]], existing_hashes: Set[str]
) -> List[Dict[str, str]]:
    """Remove suggestions already represented by ``existing_hashes``."""
    unique: List[Dict[str, str]] = []
    for item in items:
        if not item.get("suggestion"):
            continue
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
    suggest_fn: Callable[[str, str], Dict[str, Any]],
) -> List[Dict[str, str]]:
    """End-to-end review pipeline for a single document."""
    app_properties, head_revision = get_app_properties(drive_service, document_id)
    last_revision = get_last_reviewed_revision(app_properties)
    context = get_share_message(drive_service, document_id)

    current_paragraphs = get_document_paragraphs(docs_service, document_id)
    old_paragraphs: List[str] = []
    if last_revision:
        old_text = download_revision_text(drive_service, document_id, last_revision)
        old_paragraphs = old_text.splitlines()

    changed = detect_changed_ranges(old_paragraphs, current_paragraphs)
    items = process_changed_ranges(
        current_paragraphs, changed, suggest_fn, context=context
    )

    existing_list: List[str] = []
    existing_set: Set[str] = set()
    if app_properties.get(SUGGESTION_HASHES_KEY):
        existing_list = app_properties[SUGGESTION_HASHES_KEY].split(",")
        existing_set = set(existing_list)

    unique = deduplicate_suggestions(items, existing_set)
    existing_list.extend(item["hash"] for item in unique)

    available_bytes = MAX_APP_PROPERTY_BYTES - len(SUGGESTION_HASHES_KEY)
    app_properties[SUGGESTION_HASHES_KEY] = _prune_hashes(
        existing_list, max_bytes=available_bytes
    )
    update_last_reviewed_revision(app_properties, head_revision)
    update_app_properties(drive_service, document_id, app_properties)

    return unique


def post_comments(
    drive_service: Any,
    script_service: Any,
    document_id: str,
    items: List[Dict[str, str]],
) -> None:
    """Post review items as comments on the document.

    Comments contain only AI-generated feedback and are anchored to the
    relevant text range. If a comment exceeds the 4096 byte limit imposed by
    the Google Drive API, it is split into multiple parts. The first part is
    posted as a comment anchored to the text range; subsequent parts are added
    as replies to the first comment.
    """

    MAX_BYTES = 4096

    def _chunk_content(text: str) -> List[str]:
        """Split ``text`` into <= ``MAX_BYTES`` byte chunks."""
        chunks: List[str] = []
        encoded = text.encode("utf-8")
        while encoded:
            piece = encoded[:MAX_BYTES]
            chunk = piece.decode("utf-8", errors="ignore")
            chunks.append(chunk)
            encoded = encoded[len(chunk.encode("utf-8")) :]
        return chunks

    for item in items:
        lines: List[str] = []
        issue = item.get("issue")
        if issue:
            lines.append(issue)
        lines.append(item.get("suggestion", ""))
        content = "\n".join(lines)
        parts = _chunk_content(content)
        # Post the first part anchored to the text range
        comment = create_comment(
            script_service,
            document_id,
            parts[0],
            item.get("start_index"),
            item.get("end_index"),
        )
        # Post remaining parts as replies
        for part in parts[1:]:
            reply_to_comment(drive_service, document_id, comment["id"], part)
