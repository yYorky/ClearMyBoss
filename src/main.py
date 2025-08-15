"""Scheduled runner entry point for ClearMyBoss."""
from __future__ import annotations

from datetime import datetime
import logging
import time
from typing import Any

from .google_drive import build_drive_service, list_recent_docs
from .google_docs import build_docs_service
from .groq_client import get_suggestions
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


def groq_suggest(text: str, context: str) -> dict[str, str]:
    """Wrapper around :func:`get_suggestions` producing review item dicts.

    The underlying model may return clarifying questions or broader comments in
    addition to grammar and style feedback.
    """
    logger.debug(f"Getting suggestions for text length: {len(text)}, context length: {len(context) if context else 0}")
    prompt = f"{context}\n\n{text}" if context else text
    try:
        resp = get_suggestions(prompt)
        suggestion = ""
        if resp.get("choices"):
            choice = resp["choices"][0]
            suggestion = choice.get("text") or choice.get("message", {}).get("content", "")
            logger.debug(f"Received suggestion of length: {len(suggestion)}")
        else:
            logger.warning("No choices returned from Groq API")
        return {"issue": "", "suggestion": suggestion.strip(), "severity": "info"}
    except Exception as e:
        logger.error(f"Error getting suggestions from Groq: {e}")
        return {"issue": "", "suggestion": "", "severity": "info"}


def run_once(drive_service: Any, docs_service: Any, since: datetime) -> datetime:
    """Process documents changed since ``since`` and return new timestamp.

    Documents are considered changed if they were modified or newly shared with
    the service account after the provided ``since`` timestamp.
    """

    logger.info(
        "Starting document review cycle. Checking for documents changed since: %s", since
    )

    files: list[dict[str, Any]] = []
    try:
        files = list_recent_docs(drive_service, since)
        logger.info("Found %d documents to process", len(files))

        processed_count = 0
        for f in files:
            doc_id = f["id"]
            doc_name = f.get("name", "Unknown Document")
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

                processed_count += 1

            except Exception as e:
                logger.error(
                    "Error processing document '%s' (ID: %s): %s", doc_name, doc_id, e
                )
                continue

        logger.info(
            "Completed review cycle. Successfully processed %d/%d documents",
            processed_count,
            len(files),
        )

    except Exception as e:  # pragma: no cover - logging path
        logger.error(f"Error during document review cycle: {e}")

    latest_time = since
    for f in files:
        for key in ("modifiedTime", "sharedWithMeTime"):
            ts = f.get(key)
            if ts:
                try:
                    dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
                except ValueError:
                    continue
                if dt > latest_time:
                    latest_time = dt

    new_timestamp = max(latest_time, datetime.utcnow())
    logger.info(
        "Next review cycle will check for documents changed after: %s", new_timestamp
    )
    return new_timestamp


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
        
        since = datetime.utcnow()
        logger.info(f"Initial timestamp set to: {since}")
        
        import schedule
        
        def job() -> None:
            nonlocal since
            logger.info("=" * 60)
            logger.info("Scheduled job triggered - starting document review")
            since = run_once(drive_service, docs_service, since)
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
