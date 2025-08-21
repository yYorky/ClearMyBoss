"""Scheduled runner entry point for ClearMyBoss."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
import time
from typing import Any

from .google_drive import (
    build_drive_service,
    list_recent_docs,
    list_all_shared_docs,
    get_start_page_tokens,
)
from .google_docs import build_docs_service
from .groq_client import get_suggestions
from .time_utils import parse_google_timestamp
from requests import HTTPError
from .review import review_document, post_comments, review_comment_replies
from .document_cache import DocumentCache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Console output
    ]
)
logger = logging.getLogger(__name__)

DOC_CACHE_PATH = "processed_docs.json"
_DOC_CACHE = DocumentCache(DOC_CACHE_PATH)


def groq_suggest(text: str, context: str) -> dict[str, str]:
    """Wrapper around :func:`get_suggestions` producing review item dicts.

    The underlying model may return clarifying questions or broader comments in
    addition to grammar and style feedback.
    """
    logger.debug(f"Getting suggestions for text length: {len(text)}, context length: {len(context) if context else 0}")
    prompt = f"{context}\n\n{text}" if context else text
    try:
        resp = get_suggestions(prompt, retries=5, backoff=2, halt_on_429=False)
        suggestion = ""
        if resp.get("choices"):
            choice = resp["choices"][0]
            suggestion = choice.get("text") or choice.get("message", {}).get("content", "")
            logger.debug(f"Received suggestion of length: {len(suggestion)}")
        else:
            logger.warning("No choices returned from Groq API")
        return {"issue": "", "suggestion": suggestion.strip(), "severity": "info"}
    except HTTPError as e:
        status = e.response.status_code if e.response else None
        if status == 429:
            logger.warning("Rate limited by Groq: %s", e)
        else:
            logger.error("Error getting suggestions from Groq: %s", e)
        return {"issue": "", "suggestion": "", "severity": "info"}
    except Exception as e:
        logger.error(f"Error getting suggestions from Groq: {e}")
        return {"issue": "", "suggestion": "", "severity": "info"}


def _process_document(
    drive_service: Any, docs_service: Any, file: dict[str, Any]
) -> bool:
    """Review a single document and post comments.

    Parameters
    ----------
    drive_service, docs_service
        Authenticated Google Drive and Docs service instances.
    file
        File metadata dictionary returned from :func:`list_recent_docs`.

    Returns
    -------
    bool
        ``True`` if the document was processed successfully, ``False`` otherwise.
    """

    doc_id = file["id"]
    doc_name = file.get("name", "Unknown Document")
    logger.info("Processing document: '%s' (ID: %s)", doc_name, doc_id)

    try:
        items = review_document(drive_service, docs_service, doc_id, groq_suggest)
        logger.info(
            "Generated %d review items for document '%s'", len(items), doc_name
        )

        if items:
            post_comments(drive_service, doc_id, items)
            logger.info(
                "Posted %d comments to document '%s'", len(items), doc_name
            )
        else:
            logger.info("No comments to post for document '%s'", doc_name)
        review_comment_replies(drive_service, doc_id, groq_suggest)
        return True
    except Exception as e:  # pragma: no cover - logging path
        logger.error(
            "Error processing document '%s' (ID: %s): %s", doc_name, doc_id, e
        )
        return False


def _latest_timestamp(file: dict[str, Any], current: datetime) -> datetime:
    """Return the latest relevant timestamp for ``file``.

    Considers ``modifiedTime``, ``createdTime`` and ``sharedWithMeTime`` and
    returns the newest one, falling back to ``current`` when parsing fails or
    timestamps are missing.
    """

    for key in ("modifiedTime", "createdTime", "sharedWithMeTime"):
        ts = file.get(key)
        if not ts:
            continue
        try:
            dt = parse_google_timestamp(ts)
        except ValueError:
            continue
        if dt > current:
            current = dt
    return current


def run_once(
    drive_service: Any,
    docs_service: Any,
    since: datetime,
    page_tokens: dict[str, str],
    doc_cache: DocumentCache | None = None,
) -> tuple[datetime, dict[str, str]]:
    """Process documents changed since ``since`` and return new timestamp and tokens.

    Documents are considered changed if they were modified or newly shared with
    the service account after the provided ``since`` timestamp. ``page_tokens`` is
    a mapping of Drive change tokens used to query the Drive changes feed for
    permission updates across all drives.
    """

    cache = doc_cache or _DOC_CACHE

    logger.info(
        "Starting document review cycle. Checking for documents changed since: %s",
        since,
    )
    logger.info("Using change page tokens: %s", page_tokens)

    shared_docs = list_all_shared_docs(drive_service)
    current_ids = {f.get("id") for f in shared_docs if f.get("id")}
    new_shared_ids = current_ids - cache.ids
    extra_files = [f for f in shared_docs if f.get("id") in new_shared_ids]

    try:
        files, new_page_tokens = list_recent_docs(
            drive_service, since, page_tokens
        )
        logger.info(
            "Found %d documents to process (new change token: %s)",
            len(files),
            new_page_tokens,
        )
    except Exception as e:  # pragma: no cover - logging path
        logger.error(f"Error during document review cycle: {e}")
        files = []
        new_page_tokens = page_tokens

    existing_ids = {f.get("id") for f in files}
    for f in extra_files:
        fid = f.get("id")
        if fid and fid not in existing_ids:
            files.append(f)
            existing_ids.add(fid)

    processed_count = 0
    latest_time = since
    for f in files:
        latest_time = _latest_timestamp(f, latest_time)
        fid = f.get("id")
        drive_id = f.get("driveId")
        caps = f.get("capabilities")
        if fid and (drive_id is None or not isinstance(caps, dict)):
            info = (
                drive_service.files()
                .get(fileId=fid, fields="driveId,capabilities(canComment)")
                .execute(num_retries=3)
            )
            drive_id = info.get("driveId")
            caps = info.get("capabilities", {})
        can_comment = caps.get("canComment") if isinstance(caps, dict) else None
        logger.info(
            "File %s driveId=%s canComment=%s",
            fid,
            drive_id,
            can_comment,
        )
        if _process_document(drive_service, docs_service, f):
            processed_count += 1

    logger.info(
        "Completed review cycle. Successfully processed %d/%d documents",
        processed_count,
        len(files),
    )

    cache.ids = current_ids
    cache.save()

    new_timestamp = max(latest_time, datetime.utcnow())
    logger.info(
        "Next review cycle will check for documents changed after: %s",
        new_timestamp,
    )
    return new_timestamp, new_page_tokens


def main() -> None:
    """Main entry point for the ClearMyBoss application."""
    logger.info("Starting ClearMyBoss application")
    
    try:
        logger.info("Initializing Google Drive service...")
        drive_service = build_drive_service()
        logger.info("Google Drive service initialized successfully")

        logger.info("Initializing Google Docs service...")
        docs_service = build_docs_service()
        logger.info("Google Docs service initialized successfully")

        logger.info("Processing documents already shared with the service account...")
        shared_docs = list_all_shared_docs(drive_service)
        for f in shared_docs:
            _process_document(drive_service, docs_service, f)
        logger.info("Processed %d pre-existing shared documents", len(shared_docs))

        since = datetime.utcnow() - timedelta(days=7)
        logger.info(f"Initial timestamp set to: {since}")
        page_tokens = get_start_page_tokens(drive_service)
        logger.info(f"Initial change tokens set to: {page_tokens}")
        
        import schedule
        
        def job() -> None:
            nonlocal since, page_tokens
            logger.info("=" * 60)
            logger.info("Scheduled job triggered - starting document review")
            since, page_tokens = run_once(
                drive_service, docs_service, since, page_tokens, _DOC_CACHE
            )
            logger.info("Scheduled job completed")
            logger.info("=" * 60)
        
        logger.info("Setting up scheduler to run every 1 minute...")
        schedule.every(1).minutes.do(job)
        logger.info("Scheduler configured. Application is now running...")
        logger.info("Press Ctrl+C to stop the application")
        
        # Run the initial job immediately
        logger.info("Running initial document review...")
        job()
        
        while True:
            schedule.run_pending()
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Application interrupted by user. Shutting down gracefully...")
    except Exception as e:
        logger.error(f"Fatal error in main application: {e}")
        raise


if __name__ == "__main__":  # pragma: no cover
    main()
