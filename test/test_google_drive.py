"""Tests for Google Drive helpers including document listing, properties, comments, and revisions."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock
import pytest
import json

from src.google_drive import (
    download_revision_text,
    get_share_message,
    get_app_properties,
    list_recent_docs,
    reply_to_comment,
    update_app_properties,
    build_drive_service,
    list_comments,
    list_replies,
    create_comment,
)


def test_list_recent_docs_filters_by_time():
    service = MagicMock()
    service.about.return_value.get.return_value.execute.return_value = {
        "user": {"permissionId": "pid"}
    }
    service.files.return_value.list.return_value.execute.return_value = {
        "files": [
            {"id": "1", "name": "Doc1", "modifiedTime": "2024-01-01T00:00:00Z"}
        ]
    }
    service.changes.return_value.list.return_value.execute.return_value = {
        "changes": [],
        "newStartPageToken": "t1",
    }

    since = datetime(2023, 12, 31, 23, 0, 0)
    files, token = list_recent_docs(service, since, "t0")

    assert service.files.return_value.list.call_count == 1
    assert service.changes.return_value.list.call_count == 1
    assert files[0]["name"] == "Doc1"
    assert token == "t1"


def test_list_recent_docs_includes_newly_shared_docs():
    """Docs shared recently should be returned even if created long ago."""
    service = MagicMock()
    service.about.return_value.get.return_value.execute.return_value = {
        "user": {"permissionId": "pid"}
    }
    
    service.files.return_value.list.return_value.execute.return_value = {"files": []}
    service.changes.return_value.list.return_value.execute.return_value = {
        "changes": [
            {
                "file": {
                    "id": "1",
                    "name": "Shared",
                    "mimeType": "application/vnd.google-apps.document",
                    "modifiedTime": "2023-01-01T00:00:00Z",
                    "createdTime": "2023-01-02T00:00:00Z",
                    "sharedWithMeTime": "2024-01-02T00:00:00Z",
                    "permissionIds": ["pid"],
                }
            }
        ],
        "newStartPageToken": "t1",
    }

    since = datetime(2024, 1, 1, 12, 0, 0)
    files, _ = list_recent_docs(service, since, "t0")

    assert service.files.return_value.list.call_count == 1
    assert service.changes.return_value.list.call_count == 1
    assert files[0]["name"] == "Shared"


def test_list_recent_docs_parses_microsecond_timestamps():
    """Timestamps with fractional seconds should be parsed correctly."""
    service = MagicMock()
    service.about.return_value.get.return_value.execute.return_value = {
        "user": {"permissionId": "pid"}
    }
    service.files.return_value.list.return_value.execute.return_value = {
        "files": [
            {
                "id": "1",
                "name": "Micro",
                "modifiedTime": "2024-01-02T00:00:00.123456Z",
            }
        ]
    }
    service.changes.return_value.list.return_value.execute.return_value = {
        "changes": [
            {
                "file": {
                    "id": "2",
                    "name": "CreatedMicro",
                    "mimeType": "application/vnd.google-apps.document",
                    "createdTime": "2024-01-02T00:00:00.654321Z",
                    "modifiedTime": "2024-01-01T00:00:00Z",
                    "permissionIds": ["pid"],
                }
            }
        ],
        "newStartPageToken": "t1",
    }
    since = datetime(2024, 1, 1, 23, 59, 59)
    files, _ = list_recent_docs(service, since, "t0")
    assert {f["name"] for f in files} == {"Micro", "CreatedMicro"}


def test_list_recent_docs_handles_pagination():
    service = MagicMock()
    service.about.return_value.get.return_value.execute.return_value = {
        "user": {"permissionId": "pid"}
    }
    # Pages for modified docs query
    file_pages = [{"files": [], "nextPageToken": "t1"}, {"files": []}]
    # Pages for changes feed
    change_pages = [
        {"changes": [], "nextPageToken": "c1"},
        {
            "changes": [
                {
                    "file": {
                        "id": "new",
                        "name": "NewDoc",
                        "mimeType": "application/vnd.google-apps.document",
                        "createdTime": "2024-01-02T00:00:00Z",
                        "modifiedTime": "2024-01-01T00:00:00Z",
                        "permissionIds": ["pid"],
                    }
                }
            ],
            "newStartPageToken": "c2",
        },
    ]

    service.files.return_value.list.return_value.execute.side_effect = file_pages
    service.changes.return_value.list.return_value.execute.side_effect = change_pages

    since = datetime(2024, 1, 1, 12, 0, 0)
    files, token = list_recent_docs(service, since, "c0")
    assert files == [
        {
            "id": "new",
            "name": "NewDoc",
            "mimeType": "application/vnd.google-apps.document",
            "createdTime": "2024-01-02T00:00:00Z",
            "modifiedTime": "2024-01-01T00:00:00Z",
        }
    ]
    assert token == "c2"
    assert service.files.return_value.list.call_count == 2
    assert service.changes.return_value.list.call_count == 2


def test_list_recent_docs_detects_permission_changes_without_shared_time():
    service = MagicMock()
    service.about.return_value.get.return_value.execute.return_value = {
        "user": {"permissionId": "pid"}
    }
    service.files.return_value.list.return_value.execute.return_value = {"files": []}
    service.changes.return_value.list.return_value.execute.return_value = {
        "changes": [
            {
                "file": {
                    "id": "1",
                    "name": "NoSharedTime",
                    "mimeType": "application/vnd.google-apps.document",
                    "modifiedTime": "2020-01-01T00:00:00Z",
                    "createdTime": "2020-01-01T00:00:00Z",
                    "permissionIds": ["pid"],
                }
            }
        ],
        "newStartPageToken": "t1",
    }

    since = datetime(2024, 1, 1, 0, 0, 0)
    files, _ = list_recent_docs(service, since, "t0")
    assert files == [
        {
            "id": "1",
            "name": "NoSharedTime",
            "mimeType": "application/vnd.google-apps.document",
            "modifiedTime": "2020-01-01T00:00:00Z",
            "createdTime": "2020-01-01T00:00:00Z",
        }
    ]


def test_list_recent_docs_skips_changes_without_service_permission():
    service = MagicMock()
    service.about.return_value.get.return_value.execute.return_value = {
        "user": {"permissionId": "pid"}
    }
    service.files.return_value.list.return_value.execute.return_value = {"files": []}
    service.changes.return_value.list.return_value.execute.return_value = {
        "changes": [
            {
                "file": {
                    "id": "1",
                    "name": "Other",
                    "mimeType": "application/vnd.google-apps.document",
                    "permissionIds": ["other"],
                }
            }
        ],
        "newStartPageToken": "t1",
    }
    since = datetime(2024, 1, 1)
    files, token = list_recent_docs(service, since, "t0")
    assert files == []
    assert token == "t1"


def test_app_properties_roundtrip():
    service = MagicMock()
    service.files.return_value.get.return_value.execute.return_value = {
        "appProperties": {"x": "1"},
        "headRevisionId": "5",
    }
    props, rev = get_app_properties(service, "file")
    assert props == {"x": "1"}
    assert rev == "5"

    update_app_properties(service, "file", props)
    service.files.return_value.update.assert_called_once_with(
        fileId="file", body={"appProperties": props}
    )


def test_download_revision_text_decodes_bytes():
    service = MagicMock()
    service.revisions.return_value.get.return_value.execute.return_value = b"hello"
    text = download_revision_text(service, "f", "1")
    assert text == "hello"


def test_download_revision_head_uses_files_export():
    service = MagicMock()
    service.files.return_value.export.return_value.execute.return_value = b"hi"
    text = download_revision_text(service, "f", "head")
    assert text == "hi"
    service.files.return_value.export.assert_called_once_with(
        fileId="f", mimeType="text/plain"
    )
    service.revisions.return_value.get.assert_not_called()


def test_get_share_message_fetches_description():
    service = MagicMock()
    service.files.return_value.get.return_value.execute.return_value = {
        "description": "context"
    }
    msg = get_share_message(service, "file")
    assert msg == "context"
    service.files.return_value.get.assert_called_once_with(
        fileId="file", fields="description"
    )


def test_reply_to_comment():
    service = MagicMock()
    reply_to_comment(service, "file", "c1", "thanks")
    service.replies.return_value.create.assert_called_once_with(
        fileId="file", commentId="c1", body={"content": "thanks"}, fields="id"
    )


def test_list_comments_and_replies():
    service = MagicMock()
    service.comments.return_value.list.return_value.execute.return_value = {
        "comments": [{"id": "c1"}]
    }
    comments = list_comments(service, "file")
    assert comments == [{"id": "c1"}]
    service.comments.return_value.list.assert_called_once_with(
        fileId="file", fields="comments(id,author(displayName),content)"
    )

    service.replies.return_value.list.return_value.execute.return_value = {
        "replies": [{"id": "r1"}]
    }
    replies = list_replies(service, "file", "c1")
    assert replies == [{"id": "r1"}]
    service.replies.return_value.list.assert_called_once_with(
        fileId="file",
        commentId="c1",
        fields="replies(id,author(displayName),content)",
    )


def test_build_drive_service_missing_credentials(monkeypatch):
    """Should raise a clear error when credential path is not configured."""
    monkeypatch.setattr(
        "src.google_service.settings.GOOGLE_SERVICE_ACCOUNT_JSON", None
    )
    with pytest.raises(ValueError):
        build_drive_service()

def test_create_comment_calls_api(region):
    service = MagicMock()
    service.comments.return_value.create.return_value.execute.return_value = {"id": "c1"}
    result = create_comment(service, "doc", "hello", regions=[region])
    assert result == {"id": "c1"}
    body = {
        "content": "hello",
        "anchor": json.dumps({"r": "head", "a": [region]}),
    }
    service.comments.return_value.create.assert_called_once_with(
        fileId="doc", body=body, fields="id"
    )
