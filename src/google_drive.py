"""Google Drive API utilities."""
from __future__ import annotations

from datetime import datetime
import json
import os
from typing import List, Dict, Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import settings

SCOPES = ["https://www.googleapis.com/auth/drive"]


def build_drive_service() -> Any:
    """Build an authenticated Drive API service using service account credentials.

    Raises
    ------
    ValueError
        If ``GOOGLE_SERVICE_ACCOUNT_JSON`` is not set in the environment.
    FileNotFoundError
        If the path specified by ``GOOGLE_SERVICE_ACCOUNT_JSON`` does not exist.
    """

    cred_path = settings.GOOGLE_SERVICE_ACCOUNT_JSON
    if not cred_path:
        raise ValueError(
            "GOOGLE_SERVICE_ACCOUNT_JSON environment variable is not set."
        )
    if not os.path.exists(cred_path):
        raise FileNotFoundError(
            f"Service account JSON file not found at {cred_path}"
        )

    creds = service_account.Credentials.from_service_account_file(
        cred_path, scopes=SCOPES
    )
    service = build("drive", "v3", credentials=creds)
    return service


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
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(
                    tzinfo=None
                )
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
    start_index: int | None = None,
    end_index: int | None = None,
    quoted_text: str | None = None,
) -> Any:
    """Create a comment on ``file_id`` anchored to the given range.

    Parameters
    ----------
    service
        Authenticated Google Drive service instance.
    file_id
        ID of the document to comment on.
    content
        Text content of the comment.
    start_index, end_index
        Optional character offsets to anchor the comment.
    quoted_text
        Optional text snippet to attach as ``quotedFileContent`` so the comment
        highlights the exact text.
    """

    body: Dict[str, Any] = {"content": content}
    if start_index is not None and end_index is not None:
        body["anchor"] = json.dumps(
            {
                "r": {
                    "segmentId": "",
                    "startIndex": start_index,
                    "endIndex": end_index,
                }
            }
        )
    if quoted_text is not None:
        body["quotedFileContent"] = {"mimeType": "text/plain", "value": quoted_text}
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


def filter_user_comments(
    service: Any, file_id: str, ai_display_name: str
) -> List[Dict[str, Any]]:
    """Return comment threads whose latest author is not the AI reviewer."""
    comments = list_comments(service, file_id)
    user_threads: List[Dict[str, Any]] = []
    for comment in comments:
        replies = list_replies(service, file_id, comment["id"])
        last_author = (
            replies[-1].get("author", {}).get("displayName", "")
            if replies
            else comment.get("author", {}).get("displayName", "")
        )
        if last_author != ai_display_name:
            user_threads.append(comment)
    return user_threads
