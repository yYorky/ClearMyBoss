from unittest.mock import MagicMock

from src.google_apps_script import create_comment
from config import settings


def test_create_comment_invokes_script(monkeypatch):
    service = MagicMock()
    service.scripts.return_value.run.return_value.execute.return_value = {
        "response": {"result": {"id": "c1"}}
    }

    monkeypatch.setattr(settings, "GOOGLE_APPS_SCRIPT_ID", "script123")

    result = create_comment(service, "doc1", "hello", 1, 5)

    assert result == {"id": "c1"}
    service.scripts.return_value.run.assert_called_once_with(
        scriptId="script123",
        body={"function": "addComment", "parameters": ["doc1", 1, 5, "hello"]},
    )

