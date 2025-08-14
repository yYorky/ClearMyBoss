"""Google Drive API utilities."""
from __future__ import annotations

from datetime import datetime
from typing import List, Dict, Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import settings

SCOPES = ["https://www.googleapis.com/auth/drive"]


def build_drive_service() -> Any:
    """Build an authenticated Drive API service using service account credentials."""
    creds = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES
    )
    service = build("drive", "v3", credentials=creds)
    return service


def list_recent_docs(service: Any, since_time: datetime) -> List[Dict[str, Any]]:
    """Return a list of Google Docs modified after ``since_time``.

    Parameters
    ----------
    service: Authenticated Google Drive service instance.
    since_time: datetime object representing last run time.
    """
    iso_time = since_time.isoformat("T") + "Z"
    query = (
        "mimeType='application/vnd.google-apps.document' "
        f"and modifiedTime > '{iso_time}'"
    )
    results = (
        service.files()
        .list(q=query, fields="files(id, name, modifiedTime)")
        .execute()
    )
    return results.get("files", [])


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
) -> Any:
    """Create a comment on ``file_id`` anchored to the given range."""
    body: Dict[str, Any] = {"content": content}
    if start_index is not None and end_index is not None:
        body["anchor"] = f"{start_index},{end_index}"
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
        .create(fileId=file_id, commentId=comment_id, body=body)
        .execute()
    )
