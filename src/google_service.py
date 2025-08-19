from __future__ import annotations

"""Shared Google API service builder."""

from typing import Any
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import settings


def build_service(api: str, version: str, scopes: list[str]) -> Any:
    """Create an authenticated Google API client for ``api``.

    Parameters
    ----------
    api:
        Name of the Google API, e.g., ``"drive"`` or ``"docs"``.
    version:
        API version string.
    scopes:
        OAuth scopes required for the service.

    Raises
    ------
    ValueError
        If the ``GOOGLE_SERVICE_ACCOUNT_JSON`` setting is not configured.
    FileNotFoundError
        If the credential file does not exist.
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
        cred_path, scopes=scopes
    )
    return build(api, version, credentials=creds)
