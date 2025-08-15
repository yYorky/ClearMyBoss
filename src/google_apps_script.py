"""Google Apps Script Execution API utilities."""
from __future__ import annotations

from typing import Any, Dict

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import settings

SCOPES = [
    "https://www.googleapis.com/auth/script.projects",
    "https://www.googleapis.com/auth/documents",
]


def build_script_service() -> Any:
    """Build an authenticated Apps Script Execution API service."""

    creds = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES
    )
    return build("script", "v1", credentials=creds)


def create_comment(
    service: Any,
    document_id: str,
    content: str,
    start_index: int | None = None,
    end_index: int | None = None,
) -> Dict[str, str]:
    """Add a text-anchored comment via an Apps Script function.

    Parameters
    ----------
    service
        Authenticated Apps Script service instance.
    document_id
        ID of the document to comment on.
    content
        Text content of the comment.
    start_index, end_index
        Character offsets within the document's body to anchor the comment.

    Returns
    -------
    Dict containing the ``id`` of the created comment.
    """

    body: Dict[str, Any] = {
        "function": "addComment",
        "parameters": [document_id, start_index, end_index, content],
    }
    response = (
        service.scripts()
        .run(scriptId=settings.GOOGLE_APPS_SCRIPT_ID, body=body)
        .execute()
    )
    result = response.get("response", {}).get("result", {})
    if isinstance(result, dict):
        comment_id = result.get("id", "")
    else:
        comment_id = str(result)
    return {"id": comment_id}

