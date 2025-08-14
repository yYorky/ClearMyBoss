from datetime import datetime, timedelta
from unittest.mock import MagicMock

from src.google_drive import (
    download_revision_text,
    get_app_properties,
    list_recent_docs,
    update_app_properties,
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
