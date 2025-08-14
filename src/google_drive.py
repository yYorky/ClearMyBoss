"""Google Drive API utilities."""
from __future__ import annotations

from datetime import datetime
from typing import List, Dict, Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import settings

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


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
