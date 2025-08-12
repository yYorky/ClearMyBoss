from src.groq_client import get_suggestions, GROQ_API_URL


def test_get_suggestions_calls_api(monkeypatch):
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout

        class Resp:
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
