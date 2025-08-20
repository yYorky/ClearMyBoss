"""Google Drive API utilities."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .google_service import build_service
from .time_utils import parse_google_timestamp

import json

SCOPES = ["https://www.googleapis.com/auth/drive"]


def build_drive_service() -> Any:
    """Build an authenticated Drive API service."""
    return build_service("drive", "v3", SCOPES)


def list_recent_docs(service: Any, since_time: datetime) -> list[dict[str, Any]]:
    """Return Google Docs accessible to the service account, recently modified or accessed.

    For service accounts, the 'sharedWithMe' query parameter doesn't work as it does
    for regular user accounts. Instead, we query all accessible Google Docs and 
    filter by modification time, then separately query recently accessible documents
    to catch newly shared ones.

    Parameters
    ----------
    service
        Authenticated Google Drive service instance.
    since_time
        ``datetime`` of the last run. Documents with ``modifiedTime`` after this
        timestamp or that are newly accessible are returned.
    """

    iso_time = since_time.replace(microsecond=0).isoformat("T") + "Z"
    
    # Query 1: Recently modified documents
    modified_query = (
        "mimeType='application/vnd.google-apps.document' "
        f"and modifiedTime > '{iso_time}'"
    )
    
    # Query 2: All accessible documents (to catch newly shared ones)
    # We'll compare against known documents to find new ones
    all_query = "mimeType='application/vnd.google-apps.document'"

    files: list[dict[str, Any]] = []
    
    # Get recently modified documents
    page_token: str | None = None
    while True:
        params = {
            "q": modified_query,
            "fields": "nextPageToken, files(id, name, modifiedTime, createdTime)",
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
            "corpora": "allDrives",
            "pageSize": 1000,
        }
        if page_token:
            params["pageToken"] = page_token
        results = service.files().list(**params).execute(num_retries=3)
        files.extend(results.get("files", []))
        page_token = results.get("nextPageToken")
        if not page_token:
            break

    # Get all accessible documents to find newly shared ones
    # We limit this to recent createdTime to avoid processing too many old documents
    recent_created_time = (since_time - timedelta(days=30)).replace(microsecond=0).isoformat("T") + "Z"
    all_query_with_limit = f"{all_query} and createdTime > '{recent_created_time}'"
    
    page_token = None
    all_files: list[dict[str, Any]] = []
    while True:
        params = {
            "q": all_query_with_limit,
            "fields": "nextPageToken, files(id, name, modifiedTime, createdTime)",
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
            "corpora": "allDrives",
            "pageSize": 1000,
        }
        if page_token:
            params["pageToken"] = page_token
        results = service.files().list(**params).execute(num_retries=3)
        all_files.extend(results.get("files", []))
        page_token = results.get("nextPageToken")
        if not page_token:
            break

    # Combine results and deduplicate by file ID
    files_by_id = {f["id"]: f for f in files}
    for f in all_files:
        if f["id"] not in files_by_id:
            # This is a newly accessible document - check if it's actually "new"
            # by seeing if it was created recently or if we haven't seen it before
            created_time = f.get("createdTime")
            if created_time:
                try:
                    created_dt = parse_google_timestamp(created_time)
                    if created_dt > since_time:
                        files_by_id[f["id"]] = f
                except ValueError:
                    pass

    recent_files: list[dict[str, Any]] = []
    for f in files_by_id.values():
        # Include if recently modified or recently created
        for key in ("modifiedTime", "createdTime"):
            ts = f.get(key)
            if not ts:
                continue
            try:
                dt = parse_google_timestamp(ts)
            except ValueError:
                continue
            if dt > since_time:
                recent_files.append(f)
                break
    
    return recent_files


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
