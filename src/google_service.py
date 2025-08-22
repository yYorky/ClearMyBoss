from __future__ import annotations

"""Shared Google API service builder."""

from typing import Any
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import settings


def build_service(api: str, version: str, scopes: list[str]) -> Any:
    """Create an authenticated Google API client for ``api`` using OAuth.

    The client secret and token storage paths are configured via the
    ``GOOGLE_OAUTH_CLIENT_SECRET_JSON`` and ``GOOGLE_OAUTH_TOKEN_JSON``
    environment variables respectively.

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
        If either credential environment variable is not configured.
    FileNotFoundError
        If the client secret file does not exist.
    """

    client_secret_path = settings.GOOGLE_OAUTH_CLIENT_SECRET_JSON
    token_path = settings.GOOGLE_OAUTH_TOKEN_JSON
    if not client_secret_path:
        raise ValueError(
            "GOOGLE_OAUTH_CLIENT_SECRET_JSON environment variable is not set."
        )
    if not token_path:
        raise ValueError(
            "GOOGLE_OAUTH_TOKEN_JSON environment variable is not set."
        )
    if not os.path.exists(client_secret_path):
        raise FileNotFoundError(
            f"OAuth client secret JSON file not found at {client_secret_path}"
        )

    creds: Credentials | None = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                client_secret_path, scopes
            )
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())

    return build(api, version, credentials=creds)
