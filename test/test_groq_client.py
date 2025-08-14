import pytest

from src.groq_client import GROQ_API_URL, get_suggestions


def test_get_suggestions_calls_api(monkeypatch):
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout

        class Resp:
            status_code = 200
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": []}

        return Resp()

    monkeypatch.setattr("requests.post", fake_post)
    resp = get_suggestions("Some text")
    assert resp == {"choices": []}
    assert captured["url"] == GROQ_API_URL
    assert "Authorization" in captured["headers"]
    assert "Some text" in captured["json"]["prompt"]


def test_get_suggestions_retries_on_server_error(monkeypatch):
    calls = {"count": 0}

    def fake_post(url, json, headers, timeout):
        calls["count"] += 1

        class Resp:
            def __init__(self, ok):
                self.ok = ok
                self.status_code = 500 if not ok else 200

            def raise_for_status(self):
                if self.status_code >= 400:
                    from requests import HTTPError

                    raise HTTPError(response=self)

            def json(self):
                return {"choices": []}

        if calls["count"] == 1:
            return Resp(False)
        return Resp(True)

    monkeypatch.setattr("requests.post", fake_post)
    resp = get_suggestions("ok")
    assert resp == {"choices": []}
    assert calls["count"] == 2


def test_get_suggestions_raises_after_retries(monkeypatch):
    def fake_post(url, json, headers, timeout):
        from requests import RequestException

        raise RequestException("boom")

    monkeypatch.setattr("requests.post", fake_post)
    with pytest.raises(Exception):
        get_suggestions("fail", retries=2, backoff=0)
