from datetime import datetime, timedelta
from unittest.mock import MagicMock

from src.google_drive import list_recent_docs


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
