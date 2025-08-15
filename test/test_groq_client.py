import pytest

from src.groq_client import GROQ_API_URL, CHUNK_SIZE, get_suggestions
from src.main import groq_suggest


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
    msgs = captured["json"]["messages"]
    assert msgs[0]["role"] == "system"
    assert "boss" in msgs[0]["content"].lower()
    assert msgs[1]["content"].startswith("Review the following")


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


def test_groq_suggest_extracts_message_content(monkeypatch):
    def fake_get_suggestions(prompt):
        return {"choices": [{"message": {"content": "Suggestion here"}}]}

    monkeypatch.setattr("src.main.get_suggestions", fake_get_suggestions)
    result = groq_suggest("text", "context")
    assert result["suggestion"] == "Suggestion here"


def test_get_suggestions_chunks_large_text(monkeypatch):
    calls = {"count": 0}

    def fake_post(url, json, headers, timeout):
        calls["count"] += 1

        class Resp:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": "ok"}}]}

        return Resp()

    monkeypatch.setattr("requests.post", fake_post)
    large_text = "x" * (CHUNK_SIZE * 2 + 10)
    resp = get_suggestions(large_text)
    assert calls["count"] == 3
    assert resp["choices"][0]["message"]["content"] == "ok" * 3


def test_get_suggestions_retries_on_429(monkeypatch):
    calls = {"count": 0}

    def fake_post(url, json, headers, timeout):
        class Resp:
            def __init__(self, status):
                self.status_code = status
                self.headers = {"Retry-After": "1"} if status == 429 else {}

            def raise_for_status(self):
                if self.status_code >= 400:
                    from requests import HTTPError

                    raise HTTPError(response=self)

            def json(self):
                return {"choices": []}

        calls["count"] += 1
        return Resp(429 if calls["count"] == 1 else 200)

    sleeps: list[float] = []

    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr("random.uniform", lambda a, b: 0)
    monkeypatch.setattr("src.groq_client.rate_limiter.acquire", lambda: None)

    resp = get_suggestions("ok", retries=2, backoff=0.5)
    assert resp == {"choices": []}
    assert sleeps == [1.0]


def test_rate_limiter_sliding_window(monkeypatch):
    import src.groq_client as gc
    from src.groq_client import RateLimiter

    times = [0.0]
    sleeps: list[float] = []

    def fake_time():
        return times[0]

    def fake_sleep(s: float) -> None:
        sleeps.append(s)
        times[0] += s

    monkeypatch.setattr(gc.time, "time", fake_time)
    monkeypatch.setattr(gc.time, "sleep", fake_sleep)

    rl = RateLimiter(2)
    rl.acquire()  # t=0
    times[0] = 30
    rl.acquire()  # t=30
    times[0] = 50
    rl.acquire()  # third call forces 10s wait to expire first call

    assert sleeps == [10.0]


def test_rate_limiter_thread_safety(monkeypatch):
    import threading
    import src.groq_client as gc
    from src.groq_client import RateLimiter

    class FakeTime:
        def __init__(self) -> None:
            self.current = 0.0
            self.sleeps: list[float] = []
            self.lock = threading.Lock()

        def time(self) -> float:
            with self.lock:
                return self.current

        def sleep(self, s: float) -> None:
            with self.lock:
                self.sleeps.append(s)
                self.current += s

    fake = FakeTime()
    monkeypatch.setattr(gc.time, "time", fake.time)
    monkeypatch.setattr(gc.time, "sleep", fake.sleep)

    rl = RateLimiter(5)
    results: list[float] = []

    def worker() -> None:
        rl.acquire()
        results.append(fake.time())

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    early = [t for t in results if t < 60]
    later = [t for t in results if t >= 60]

    assert len(early) == 5
    assert len(later) == 5
    assert fake.sleeps == [60]
