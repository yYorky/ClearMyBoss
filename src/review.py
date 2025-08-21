"""Core review pipeline for detecting changes and posting feedback.

This module orchestrates document analysis, suggestion generation, de-
duplication, and comment posting.
"""

from __future__ import annotations

from typing import Any, Callable
import hashlib
import logging
import time
from difflib import SequenceMatcher
from googleapiclient.errors import HttpError

from .google_docs import chunk_paragraphs, get_document_paragraphs
from .google_drive import (
    download_revision_text,
    get_app_properties,
    get_share_message,
    update_app_properties,
    reply_to_comment,
    create_comment,
    list_comments,
    list_replies,
)


# Maximum allowed bytes for a single app property (key + value).
MAX_APP_PROPERTY_BYTES = 124

SUGGESTION_HASHES_KEY = "suggestionHashes"


def detect_changed_ranges(
    old_paragraphs: list[str], new_paragraphs: list[str]
) -> list[tuple[int, int]]:
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
    ranges: list[tuple[int, int]] = []
    for tag, _, _, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            ranges.append((j1, j2 - 1))
    return ranges


def process_changed_ranges(
    paragraphs: list[str],
    changed_ranges: list[tuple[int, int]],
    suggest_fn: Callable[[str, str], dict[str, Any]],
    context: str = "",
    chunk_chars: int = 800,
) -> list[dict[str, str]]:
    """Run ``suggest_fn`` on changed text ranges and format results.

    Each changed range is further divided into chunks using
    :func:`src.google_docs.chunk_paragraphs` so that large edits produce
    multiple concise comments.
    """
    # Pre-compute cumulative character offsets for each paragraph so we can
    # derive ``start_index``/``end_index`` for changed ranges.
    offsets: list[int] = [0]
    for para in paragraphs:
        # Account for the trailing newline that separates paragraphs in the
        # document's plain-text representation.
        offsets.append(offsets[-1] + len(para) + 1)

    items: list[dict[str, str]] = []
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
    """Return a short hash used to identify duplicate suggestions."""

    return hashlib.sha1(f"{suggestion}|{quote}".encode()).hexdigest()[:8]


def _prune_hashes(hashes: list[str], max_bytes: int = 124) -> str:
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


def split_into_byte_chunks(text: str, max_bytes: int) -> list[str]:
    """Split ``text`` into UTF-8 safe chunks each no larger than ``max_bytes``."""

    chunks: list[str] = []
    encoded = text.encode("utf-8")
    while encoded:
        piece = encoded[:max_bytes]
        chunk = piece.decode("utf-8", errors="ignore")
        chunks.append(chunk)
        encoded = encoded[len(chunk.encode("utf-8")) :]
    return chunks


def deduplicate_suggestions(
    items: list[dict[str, str]], existing_hashes: set[str]
) -> list[dict[str, str]]:
    """Remove suggestions already represented by ``existing_hashes``."""
    unique: list[dict[str, str]] = []
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


def _retry_with_backoff(
    fn: Callable[..., Any],
    *args: Any,
    max_attempts: int = 5,
    base_delay: float = 1.0,
    **kwargs: Any,
) -> Any:
    """Call ``fn`` retrying on 429 or 5xx ``HttpError`` responses.

    Uses exponential backoff with ``base_delay`` seconds and up to
    ``max_attempts`` attempts. Raises the last exception if all retries
    fail.
    """

    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except HttpError as exc:  # pragma: no cover - network errors hard to simulate
            status = int(getattr(getattr(exc, "resp", None), "status", 0))
            retryable = status == 429 or 500 <= status < 600
            if retryable and attempt < max_attempts - 1:
                delay = base_delay * (2**attempt)
                logging.warning(
                    "Retrying %s due to HTTP %s (attempt %d/%d)",
                    fn.__name__,
                    status,
                    attempt + 1,
                    max_attempts,
                )
                time.sleep(delay)
                continue
            raise


def review_document(
    drive_service: Any,
    docs_service: Any,
    document_id: str,
    suggest_fn: Callable[[str, str], dict[str, Any]],
) -> list[dict[str, str]]:
    """End-to-end review pipeline for a single document."""
    app_properties, head_revision = get_app_properties(drive_service, document_id)
    last_revision = app_properties.get("lastReviewedRevisionId")
    context = get_share_message(drive_service, document_id)

    current_paragraphs = get_document_paragraphs(docs_service, document_id)
    old_paragraphs: list[str] = []
    if last_revision:
        old_text = download_revision_text(drive_service, document_id, last_revision)
        old_paragraphs = old_text.splitlines()

    changed = detect_changed_ranges(old_paragraphs, current_paragraphs)
    items = process_changed_ranges(
        current_paragraphs, changed, suggest_fn, context=context
    )

    existing_list: list[str] = []
    existing_set: set[str] = set()
    if app_properties.get(SUGGESTION_HASHES_KEY):
        existing_list = app_properties[SUGGESTION_HASHES_KEY].split(",")
        existing_set = set(existing_list)

    unique = deduplicate_suggestions(items, existing_set)
    existing_list.extend(item["hash"] for item in unique)

    available_bytes = MAX_APP_PROPERTY_BYTES - len(SUGGESTION_HASHES_KEY)
    app_properties[SUGGESTION_HASHES_KEY] = _prune_hashes(
        existing_list, max_bytes=available_bytes
    )
    app_properties["lastReviewedRevisionId"] = head_revision
    update_app_properties(drive_service, document_id, app_properties)

    return unique


def post_comments(
    drive_service: Any,
    document_id: str,
    items: list[dict[str, str]],
) -> None:
    """Post review items as comments on the document.

    Comments contain only AI-generated feedback and are anchored to the
    relevant text range. If a comment exceeds the 4096 byte limit imposed by
    the Google Drive API, it is split into multiple parts. The first part is
    posted as a comment anchored to the text range; subsequent parts are added
    as replies to the first comment.
    """

    MAX_BYTES = 4096
    # Retrieve plain text of the latest revision so we can derive line numbers
    document_text = download_revision_text(drive_service, document_id, "head")

    for item in items:
        lines: list[str] = []
        issue = item.get("issue")
        if issue:
            lines.append(issue)
        lines.append(item.get("suggestion", ""))
        content = "\n".join(lines)
        parts = split_into_byte_chunks(content, MAX_BYTES)
        # Post the first part anchored to the text range
        start = item.get("start_index")
        end = item.get("end_index")
        regions = None
        if start is not None and end is not None:
            start_line = document_text.count("\n", 0, start) + 1
            end_line = document_text.count("\n", 0, max(end - 1, 0)) + 1
            line_count = end_line - start_line + 1
            regions = [{"line": {"n": start_line, "l": line_count}}]
        try:
            comment = _retry_with_backoff(
                create_comment,
                drive_service,
                document_id,
                parts[0],
                revision_id="head",
                regions=regions,
            )
        except Exception:
            logging.exception("Failed to create comment for %s", document_id)
            continue
        # Post remaining parts as replies
        for part in parts[1:]:
            try:
                _retry_with_backoff(
                    reply_to_comment,
                    drive_service,
                    document_id,
                    comment["id"],
                    part,
                )
            except Exception:
                logging.exception(
                    "Failed to reply to comment %s for %s",
                    comment.get("id"),
                    document_id,
                )


def review_comment_replies(
    drive_service: Any, doc_id: str, review_fn: Callable[[str, str], dict[str, Any]]
) -> None:
    """Evaluate replies to the service account's comments.

    For each comment thread authored by the service account, new replies are
    passed to ``review_fn``. The function may return a ``reply`` string to post
    guidance and a ``resolve`` flag to mark the thread as resolved.
    """

    try:
        about = (
            drive_service.about()
            .get(fields="user(displayName)")
            .execute(num_retries=3)
        )
        author_name = about.get("user", {}).get("displayName", "")
    except Exception:
        logging.exception("Failed to fetch service account display name")
        author_name = ""

    threads = list_comments(drive_service, doc_id)
    for thread in threads:
        if thread.get("author", {}).get("displayName") != author_name:
            continue
        comment_id = thread.get("id")
        replies = list_replies(drive_service, doc_id, comment_id)
        last_own_reply = -1
        for idx, rep in enumerate(replies):
            if rep.get("author", {}).get("displayName") == author_name:
                last_own_reply = idx
        for reply in replies[last_own_reply + 1 :]:
            if reply.get("author", {}).get("displayName") == author_name:
                continue
            review = review_fn(reply.get("content", ""), thread.get("content", ""))
            if not isinstance(review, dict):
                continue
            response = review.get("reply") or review.get("response")
            resolve = review.get("resolve")
            if response:
                try:
                    _retry_with_backoff(
                        reply_to_comment, drive_service, doc_id, comment_id, response
                    )
                except Exception:
                    logging.exception(
                        "Failed to reply to comment %s for %s", comment_id, doc_id
                    )
            if resolve:
                try:
                    def _resolve_comment(
                        service: Any, file_id: str, comment_id: str
                    ) -> Any:
                        return (
                            service.comments()
                            .update(
                                fileId=file_id,
                                commentId=comment_id,
                                body={"resolved": True},
                                fields="id",
                            )
                            .execute(num_retries=3)
                        )

                    _retry_with_backoff(_resolve_comment, drive_service, doc_id, comment_id)
                except Exception:
                    logging.exception(
                        "Failed to resolve comment %s for %s", comment_id, doc_id
                    )
