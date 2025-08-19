"""Google Drive API utilities."""
from __future__ import annotations

from datetime import datetime
from typing import List, Dict, Any

from .google_service import build_service
from .time_utils import parse_google_timestamp

import json

SCOPES = ["https://www.googleapis.com/auth/drive"]


def build_drive_service() -> Any:
    """Build an authenticated Drive API service."""
    return build_service("drive", "v3", SCOPES)


def list_recent_docs(service: Any, since_time: datetime) -> List[Dict[str, Any]]:
    """Return Google Docs modified or shared after ``since_time``.

    The Drive API does not support filtering by ``sharedWithMeTime`` in the
    query, so we retrieve all documents either modified after the timestamp or
    currently shared with the account and then filter the results locally.

    Parameters
    ----------
    service
        Authenticated Google Drive service instance.
    since_time
        ``datetime`` of the last run. Documents with ``modifiedTime`` or
        ``sharedWithMeTime`` after this timestamp are returned.
    """

    iso_time = since_time.replace(microsecond=0).isoformat("T") + "Z"
    query = (
        "mimeType='application/vnd.google-apps.document' "
        f"and (modifiedTime > '{iso_time}' or sharedWithMe = true)"
    )
    results = (
        service.files()
        .list(
            q=query,
            fields="files(id, name, modifiedTime, sharedWithMeTime)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora="allDrives",
        )
        .execute()
    )
    files = results.get("files", [])
    recent_files: List[Dict[str, Any]] = []
    for f in files:
        for key in ("modifiedTime", "sharedWithMeTime"):
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


def get_app_properties(service: Any, file_id: str) -> tuple[Dict[str, str], str]:
    """Return ``appProperties`` and ``headRevisionId`` for ``file_id``."""
    result = (
        service.files()
        .get(fileId=file_id, fields="appProperties, headRevisionId")
        .execute()
    )
    return result.get("appProperties", {}), result.get("headRevisionId", "")


def update_app_properties(
    service: Any, file_id: str, app_properties: Dict[str, str]
) -> None:
    """Update ``appProperties`` for ``file_id``."""
    service.files().update(
        fileId=file_id, body={"appProperties": app_properties}
    ).execute()


def download_revision_text(service: Any, file_id: str, revision_id: str) -> str:
    """Download revision content as plain text."""
    content = (
        service.revisions()
        .get(fileId=file_id, revisionId=revision_id, alt="media")
        .execute()
    )
    if isinstance(content, bytes):
        return content.decode()
    return content


def get_share_message(service: Any, file_id: str) -> str:
    """Return the file's description to use as share message context."""
    result = (
        service.files()
        .get(fileId=file_id, fields="description")
        .execute()
    )
    return result.get("description", "")


def create_comment(
    service: Any,
    file_id: str,
    content: str,
    revision_id: str = "head",
    regions: List[dict] | None = None,
) -> Dict[str, str]:
    """Create a comment on ``file_id`` optionally anchored to a text range."""
    body: Dict[str, Any] = {"content": content}
    anchor_dict: Dict[str, Any] = {"r": revision_id}
    if regions is not None:
        anchor_dict["a"] = regions
    body["anchor"] = json.dumps(anchor_dict)
    return (
        service.comments()
        .create(fileId=file_id, body=body, fields="id")
        .execute()
    )


def reply_to_comment(
    service: Any, file_id: str, comment_id: str, content: str
) -> Any:
    """Reply to an existing comment thread."""
    body = {"content": content}
    return (
        service.replies()
        .create(fileId=file_id, commentId=comment_id, body=body, fields="id")
        .execute()
    )


def list_comments(service: Any, file_id: str) -> List[Dict[str, Any]]:
    """Return top-level comments for ``file_id``."""
    result = (
        service.comments()
        .list(fileId=file_id, fields="comments(id,author(displayName),content)")
        .execute()
    )
    return result.get("comments", [])


def list_replies(service: Any, file_id: str, comment_id: str) -> List[Dict[str, Any]]:
    """Return replies for a given comment."""
    result = (
        service.replies()
        .list(
            fileId=file_id,
            commentId=comment_id,
            fields="replies(id,author(displayName),content)",
        )
        .execute()
    )
    return result.get("replies", [])
