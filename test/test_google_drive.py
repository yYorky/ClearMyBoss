from datetime import datetime, timedelta
from unittest.mock import MagicMock
import json
import pytest

from src.google_drive import (
    download_revision_text,
    create_comment,
    get_share_message,
    get_app_properties,
    list_recent_docs,
    reply_to_comment,
    update_app_properties,
    build_drive_service,
    list_comments,
    list_replies,
    filter_user_comments,
)


def test_list_recent_docs_filters_by_time():
    service = MagicMock()
    service.files.return_value.list.return_value.execute.return_value = {
        "files": [
            {"id": "1", "name": "Doc1", "modifiedTime": "2024-01-01T00:00:00Z"}
        ]
    }
    since = datetime.utcnow() - timedelta(days=1)
    files = list_recent_docs(service, since)
    service.files.assert_called_once()
    assert files[0]["name"] == "Doc1"


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


def test_create_and_reply_comment():
    service = MagicMock()
    create_comment(service, "file", "hello", 1, 5)
    expected_anchor = json.dumps(
        {"r": {"segmentId": "", "startIndex": 1, "endIndex": 5}}
    )
    service.comments.return_value.create.assert_called_once_with(
        fileId="file", body={"content": "hello", "anchor": expected_anchor}, fields="id"
    )

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


def test_filter_user_comments_skips_ai_threads():
    service = MagicMock()
    service.comments.return_value.list.return_value.execute.return_value = {
        "comments": [
            {"id": "c1", "author": {"displayName": "User1"}},
            {"id": "c2", "author": {"displayName": "BossBot"}},
            {"id": "c3", "author": {"displayName": "User2"}},
        ]
    }
    service.replies.return_value.list.return_value.execute.side_effect = [
        {"replies": [{"author": {"displayName": "BossBot"}}]},
        {"replies": []},
        {"replies": [{"author": {"displayName": "User2"}}]},
    ]
    threads = filter_user_comments(service, "file", "BossBot")
    assert [c["id"] for c in threads] == ["c3"]


def test_build_drive_service_missing_credentials(monkeypatch):
    """Should raise a clear error when credential path is not configured."""
    monkeypatch.setattr(
        "src.google_drive.settings.GOOGLE_SERVICE_ACCOUNT_JSON", None
    )
    with pytest.raises(ValueError):
        build_drive_service()
