from unittest.mock import MagicMock

from src.google_apps_script import create_anchored_comment
from config import settings
import pytest


def test_create_anchored_comment_invokes_script(monkeypatch):
    service = MagicMock()
    service.scripts.return_value.run.return_value.execute.return_value = {
        "response": {"result": {"id": "c1"}}
    }

    monkeypatch.setattr(settings, "GOOGLE_APPS_SCRIPT_ID", "script123")

    anchor = {"startIndex": 1, "endIndex": 5}
    result = create_anchored_comment(service, "doc1", "hello", anchor)

    assert result == {"id": "c1"}
    service.scripts.return_value.run.assert_called_once_with(
        scriptId="script123",
        body={
            "function": "addAnchoredComment",
            "parameters": ["doc1", anchor, "hello"],
        },
    )


def test_create_anchored_comment_requires_script_id(monkeypatch):
    service = MagicMock()
    monkeypatch.setattr(settings, "GOOGLE_APPS_SCRIPT_ID", None)
    with pytest.raises(ValueError):
        create_anchored_comment(service, "doc1", "hi", {"startIndex": 1, "endIndex": 2})

