"""Google Drive API utilities."""
from __future__ import annotations

from datetime import datetime
import json
import logging
from typing import Any

from .google_service import build_service
from .time_utils import parse_google_timestamp

SCOPES = ["https://www.googleapis.com/auth/drive"]

logger = logging.getLogger(__name__)


def build_drive_service() -> Any:
    """Build an authenticated Drive API service."""
    return build_service("drive", "v3", SCOPES)


def list_recent_changes(
    service: Any, page_token: str
) -> tuple[list[dict[str, Any]], str]:
    """Return files whose metadata or permissions changed since ``page_token``.

    Parameters
    ----------
    service
        Authenticated Google Drive service instance.
    page_token
        Change page token retrieved from ``changes().getStartPageToken``.
    """

    logger.info("Fetching Drive changes starting from page token %s", page_token)
    files: list[dict[str, Any]] = []
    token = page_token
    while True:
        params = {
            "pageToken": token,
            "fields": (
                "nextPageToken,newStartPageToken,"
                "changes(file(id,name,mimeType,modifiedTime,createdTime,sharedWithMeTime))"
            ),
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
            "pageSize": 1000,
        }
        results = service.changes().list(**params).execute(num_retries=3)
        changes = results.get("changes", [])
        logger.info(
            "Retrieved %d change records (nextPageToken=%s)",
            len(changes),
            results.get("nextPageToken"),
        )
        for change in changes:
            file = change.get("file")
            if file and file.get("mimeType") == "application/vnd.google-apps.document":
                files.append(file)
        token = results.get("nextPageToken")
        if not token:
            new_token = results.get("newStartPageToken", page_token)
            logger.info(
                "Finished fetching changes. %d document entries collected. New token %s",
                len(files),
                new_token,
            )
            return files, new_token


def list_recent_docs(
    service: Any, since_time: datetime, page_token: str
) -> tuple[list[dict[str, Any]], str]:
    """Return Google Docs changed or shared since ``since_time`` and ``page_token``.

    Parameters
    ----------
    service
        Authenticated Google Drive service instance.
    since_time
        ``datetime`` of the last run. Documents with ``modifiedTime`` after this
        timestamp are returned.
    page_token
        Change page token from the previous run used to query the changes feed.
    """

    iso_time = since_time.replace(microsecond=0).isoformat("T") + "Z"

    modified_query = (
        "mimeType='application/vnd.google-apps.document' "
        f"and modifiedTime > '{iso_time}'"
    )

    logger.info("Listing docs with modifiedTime after %s", iso_time)

    files: list[dict[str, Any]] = []

    # Fetch recently modified docs
    file_page: str | None = None
    while True:
        params = {
            "q": modified_query,
            "fields": (
                "nextPageToken, files(id,name,modifiedTime,createdTime,sharedWithMeTime)"
            ),
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
            "corpora": "allDrives",
            "pageSize": 1000,
        }
        if file_page:
            params["pageToken"] = file_page
        results = service.files().list(**params).execute(num_retries=3)
        batch = results.get("files", [])
        files.extend(batch)
        logger.info(
            "Retrieved %d modified docs (nextPageToken=%s)",
            len(batch),
            results.get("nextPageToken"),
        )
        file_page = results.get("nextPageToken")
        if not file_page:
            break

    logger.info("Total %d docs from modifiedTime query", len(files))

    # Fetch changes to catch newly shared docs
    change_files, new_page_token = list_recent_changes(service, page_token)
    logger.info(
        "Change feed returned %d docs; new change token %s",
        len(change_files),
        new_page_token,
    )

    files_by_id = {f["id"]: f for f in files}
    for f in change_files:
        fid = f.get("id")
        if not fid:
            continue
        f["_include_unconditionally"] = True
        if fid not in files_by_id:
            files_by_id[fid] = f
        else:
            files_by_id[fid].update(f)
            files_by_id[fid]["_include_unconditionally"] = True

    recent_files: list[dict[str, Any]] = []
    for f in files_by_id.values():
        fid = f.get("id")
        name = f.get("name")
        timestamps = {
            key: f.get(key)
            for key in ("modifiedTime", "createdTime", "sharedWithMeTime")
        }
        logger.debug(
            "Evaluating file %s (%s) with timestamps %s", fid, name, timestamps
        )
        include = f.pop("_include_unconditionally", False)
        missing_keys = [k for k, v in timestamps.items() if not v]
        newer_found = False
        if not include:
            for key, ts in timestamps.items():
                if not ts:
                    continue
                try:
                    dt = parse_google_timestamp(ts)
                except ValueError:
                    logger.debug(
                        "File %s (%s) has invalid %s: %s", fid, name, key, ts
                    )
                    continue
                if dt > since_time:
                    include = True
                    newer_found = True
                    break
        if not include:
            reasons: list[str] = []
            if missing_keys:
                reasons.extend(f"{k} missing" for k in missing_keys)
            if not newer_found and len(missing_keys) < 3:
                reasons.append("no timestamps newer than cutoff")
            if not reasons:
                reasons.append("no timestamps available")
            logger.debug(
                "Excluding file %s (%s): %s", fid, name, "; ".join(reasons)
            )
        else:
            recent_files.append(f)

    logger.info("Returning %d documents after filtering", len(recent_files))

    return recent_files, new_page_token


def get_app_properties(service: Any, file_id: str) -> tuple[dict[str, str], str]:
    """Return ``appProperties`` and ``headRevisionId`` for ``file_id``."""
    result = (
        service.files()
        .get(fileId=file_id, fields="appProperties, headRevisionId")
        .execute(num_retries=3)
    )
    return result.get("appProperties", {}), result.get("headRevisionId", "")


def update_app_properties(
    service: Any, file_id: str, app_properties: dict[str, str]
) -> None:
    """Update ``appProperties`` for ``file_id``."""
    service.files().update(
        fileId=file_id, body={"appProperties": app_properties}
    ).execute(num_retries=3)


def download_revision_text(service: Any, file_id: str, revision_id: str) -> str:
    """Download revision content as plain text."""
    if revision_id == "head":
        content = (
            service.files()
            .export(fileId=file_id, mimeType="text/plain")
            .execute(num_retries=3)
        )
    else:
        content = (
            service.revisions()
            .get(fileId=file_id, revisionId=revision_id, alt="media")
            .execute(num_retries=3)
        )
    if isinstance(content, bytes):
        return content.decode()
    if isinstance(content, str):
        return content
    return str(content)


def get_share_message(service: Any, file_id: str) -> str:
    """Return the file's description to use as share message context."""
    result = (
        service.files()
        .get(fileId=file_id, fields="description")
        .execute(num_retries=3)
    )
    return result.get("description", "")


def create_comment(
    service: Any,
    file_id: str,
    content: str,
    revision_id: str = "head",
    regions: list[dict] | None = None,
) -> dict[str, str]:
    """Create a comment on ``file_id`` optionally anchored to a text range."""
    body: dict[str, Any] = {"content": content}
    anchor_dict: dict[str, Any] = {"r": revision_id}
    if regions is not None:
        anchor_dict["a"] = regions
    body["anchor"] = json.dumps(anchor_dict)
    return (
        service.comments()
        .create(fileId=file_id, body=body, fields="id")
        .execute(num_retries=3)
    )


def reply_to_comment(
    service: Any, file_id: str, comment_id: str, content: str
) -> Any:
    """Reply to an existing comment thread."""
    body = {"content": content}
    return (
        service.replies()
        .create(fileId=file_id, commentId=comment_id, body=body, fields="id")
        .execute(num_retries=3)
    )


def list_comments(service: Any, file_id: str) -> list[dict[str, Any]]:
    """Return top-level comments for ``file_id``."""
    result = (
        service.comments()
        .list(fileId=file_id, fields="comments(id,author(displayName),content)")
        .execute(num_retries=3)
    )
    return result.get("comments", [])


def list_replies(service: Any, file_id: str, comment_id: str) -> list[dict[str, Any]]:
    """Return replies for a given comment."""
    result = (
        service.replies()
        .list(
            fileId=file_id,
            commentId=comment_id,
            fields="replies(id,author(displayName),content)",
        )
        .execute(num_retries=3)
    )
    return result.get("replies", [])
