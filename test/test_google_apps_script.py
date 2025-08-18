from unittest.mock import MagicMock

from src.google_apps_script import create_anchored_comment


def test_create_anchored_comment(monkeypatch):
    monkeypatch.setattr(
        "src.google_apps_script.settings.GOOGLE_APPS_SCRIPT_ID", "script123"
    )
    service = MagicMock()
    service.scripts.return_value.run.return_value.execute.return_value = {
        "response": {"result": {"id": "c1"}}
    }
    anchor = {"segmentId": "", "startIndex": 1, "endIndex": 3}
    result = create_anchored_comment(service, "doc", "hello", anchor)
    assert result == {"id": "c1"}
    body = {
        "function": "addAnchoredComment",
        "parameters": ["doc", anchor, "hello"],
    }
    service.scripts.return_value.run.assert_called_once_with(
        scriptId="script123", body=body
    )
