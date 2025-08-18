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


def create_anchored_comment(
    service: Any,
    document_id: str,
    content: str,
    anchor: Dict[str, int] | None = None,
) -> Dict[str, str]:
    """Add an anchored comment via an Apps Script function.

    Parameters
    ----------
    service
        Authenticated Apps Script service instance.
    document_id
        ID of the document to comment on.
    content
        Text content of the comment.
    anchor
        JSON dict specifying the text range to anchor the comment. The dict
        should include ``startIndex`` and ``endIndex`` keys.

    Returns
    -------
    Dict containing the ``id`` of the created comment.
    """
    script_id = settings.GOOGLE_APPS_SCRIPT_ID
    if not script_id:
        raise ValueError("GOOGLE_APPS_SCRIPT_ID is not set")

    body: Dict[str, Any] = {
        "function": "addAnchoredComment",
        "parameters": [document_id, anchor, content],
    }
    response = service.scripts().run(scriptId=script_id, body=body).execute()
    result = response.get("response", {}).get("result", {})
    if isinstance(result, dict):
        comment_id = result.get("id", "")
    else:
        comment_id = str(result)
    return {"id": comment_id}

