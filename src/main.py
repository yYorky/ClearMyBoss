"""Scheduled runner entry point for ClearMyBoss."""
from __future__ import annotations

from datetime import datetime
import json
import logging
import time
from pathlib import Path
from typing import Any

from .google_drive import build_drive_service, list_recent_docs
from .google_docs import build_docs_service
from .groq_client import get_suggestions
from .time_utils import parse_google_timestamp
from requests import HTTPError
from .review import review_document, post_comments

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Console output
    ]
)
logger = logging.getLogger(__name__)


# State file for storing Drive change token and timestamp
STATE_FILE = Path("last_change_token.json")


def load_state(drive_service: Any) -> tuple[str, datetime]:
    """Return stored change token and timestamp.

    Parameters
    ----------
    drive_service
        Authenticated Drive service used to obtain an initial token when no
        state file exists.
    """

    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            token = data.get("page_token")
            ts_str = data.get("timestamp")
            if token:
                if ts_str:
                    try:
                        return token, datetime.fromisoformat(ts_str)
                    except ValueError:
                        return token, datetime.utcnow()
                return token, datetime.utcnow()
        except Exception:  # pragma: no cover - logging path
            pass

    # No existing state or token missing; obtain a fresh token
    resp = (
        drive_service.changes()
        .getStartPageToken()
        .execute(num_retries=3)
    )
    token = resp.get("startPageToken", "")
    return token, datetime.utcnow()


def save_state(token: str, timestamp: datetime) -> None:
    """Persist ``token`` and ``timestamp`` to ``STATE_FILE``."""

    data = {
        "page_token": token,
        "timestamp": timestamp.isoformat(),
    }
    STATE_FILE.write_text(json.dumps(data))


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
    page_token: str,
) -> tuple[str, datetime]:
    """Process recent documents and return new Drive change token and timestamp.

    Documents are considered changed if they were modified or newly shared with
    the service account after the provided ``since`` timestamp.  The Drive change
    ``page_token`` is advanced at the end of each run using
    ``changes().getStartPageToken`` so the caller can persist it for future
    executions.
    """

    logger.info(
        "Starting document review cycle. Checking for documents changed since: %s", since
    )

    try:
        files = list_recent_docs(drive_service, since)
        logger.info("Found %d documents to process", len(files))
    except Exception as e:  # pragma: no cover - logging path
        logger.error(f"Error during document review cycle: {e}")
        files = []

    processed_count = 0
    latest_time = since
    for f in files:
        latest_time = _latest_timestamp(f, latest_time)
        if _process_document(drive_service, docs_service, f):
            processed_count += 1

    logger.info(
        "Completed review cycle. Successfully processed %d/%d documents",
        processed_count,
        len(files),
    )

    new_timestamp = max(latest_time, datetime.utcnow())
    logger.info(
        "Next review cycle will check for documents changed after: %s", new_timestamp
    )

    # Advance and return a fresh change token so state can be persisted
    try:
        resp = (
            drive_service.changes()
            .getStartPageToken()
            .execute(num_retries=3)
        )
        new_token = resp.get("startPageToken", page_token)
    except Exception as e:  # pragma: no cover - logging path
        logger.error("Error obtaining Drive change token: %s", e)
        new_token = page_token

    return new_token, new_timestamp


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

        page_token, since = load_state(drive_service)
        logger.info(
            "Loaded state: page_token=%s, since=%s", page_token, since
        )

        import schedule

        def job() -> None:
            nonlocal since, page_token
            logger.info("=" * 60)
            logger.info("Scheduled job triggered - starting document review")
            page_token, since = run_once(
                drive_service, docs_service, since, page_token
            )
            save_state(page_token, since)
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
