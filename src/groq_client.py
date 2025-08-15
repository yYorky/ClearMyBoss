"""Simple Groq API client for grammar suggestions."""
from __future__ import annotations

from typing import Any, Dict, Iterable

import logging
import time
import threading
import random
import requests
from requests.exceptions import HTTPError, RequestException

from config import settings

logger = logging.getLogger(__name__)

# Groq's OpenAI-compatible endpoint for chat completions
# https://console.groq.com/docs shows that the API mirrors OpenAI's
# `/chat/completions` route rather than the legacy `/completions` path.
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
# Prompt sent with each request
PROMPT_TEMPLATE = "Review the following text for grammar and style:\n\n{text}"
# System instruction to keep the model's feedback brief and relevant
SYSTEM_PROMPT = (
    "You are a no-nonsense boss reviewing your employee's work. "
    "Provide direct, actionable feedback on the text."
)
# Maximum bytes of text per request. Default tested at 20KB. Can be overridden via
# ``GROQ_CHUNK_SIZE`` environment variable.
CHUNK_SIZE = settings.GROQ_CHUNK_SIZE


class RateLimiter:
    """Simple token bucket style rate limiter.

    Ensures no more than ``requests_per_minute`` calls are made in any 60
    second window by sleeping as needed before allowing each request to
    proceed. Thread-safe so multiple threads can share the limiter.
    """

    def __init__(self, requests_per_minute: int) -> None:
        self.interval = 60.0 / max(1, requests_per_minute)
        self.lock = threading.Lock()
        self.last_time = 0.0

    def acquire(self) -> None:
        with self.lock:
            now = time.time()
            wait = self.last_time + self.interval - now
            if wait > 0:
                time.sleep(wait)
            self.last_time = time.time()


rate_limiter = RateLimiter(settings.GROQ_REQUESTS_PER_MINUTE)

def get_suggestions(
    text: str,
    prompt_template: str = PROMPT_TEMPLATE,
    *,
    retries: int = 3,
    backoff: float = 1.0,
) -> Dict[str, Any]:
    """Fetch grammar suggestions from Groq.

    Large texts are split into ``CHUNK_SIZE`` pieces to keep each request
    well below Groq's payload limits. The returned suggestion combines the
    responses from all chunks.
    """

    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    def _post(prompt: str) -> Dict[str, Any]:
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 800,
        }

        last_exc = None
        _backoff = backoff
        for attempt in range(1, retries + 1):
            try:
                rate_limiter.acquire()
                resp = requests.post(
                    GROQ_API_URL, json=payload, headers=headers, timeout=30
                )
                if resp.status_code >= 400:
                    try:
                        detail = resp.json()
                    except Exception:
                        detail = {"text": resp.text}
                    resp.raise_for_status()
                return resp.json()

            except HTTPError as exc:
                status = exc.response.status_code if exc.response else None
                try:
                    err_body = exc.response.json()
                except Exception:
                    err_body = {"text": getattr(exc.response, "text", "")}
                if status == 429 and attempt < retries:
                    retry_after = (
                        exc.response.headers.get("Retry-After")
                        if exc.response
                        else None
                    )
                    try:
                        wait = float(retry_after)
                    except (TypeError, ValueError):
                        wait = _backoff
                    jitter = random.uniform(0, wait / 2)
                    logger.warning(
                        "Groq rate limited (429). Retrying in %.2f seconds (attempt %s/%s)",
                        wait + jitter,
                        attempt,
                        retries,
                    )
                    time.sleep(wait + jitter)
                    _backoff *= 2
                elif status and 500 <= status < 600 and attempt < retries:
                    jitter = random.uniform(0, _backoff / 2)
                    logger.warning(
                        "Groq HTTP %s. Retrying in %.2f seconds (attempt %s/%s)",
                        status,
                        _backoff + jitter,
                        attempt,
                        retries,
                    )
                    time.sleep(_backoff + jitter)
                    _backoff *= 2
                else:
                    raise

            except RequestException as exc:
                last_exc = exc
                if attempt < retries:
                    jitter = random.uniform(0, _backoff / 2)
                    logger.warning(
                        "Request error %s. Retrying in %.2f seconds (attempt %s/%s)",
                        exc,
                        _backoff + jitter,
                        attempt,
                        retries,
                    )
                    time.sleep(_backoff + jitter)
                    _backoff *= 2
                else:
                    raise last_exc

    def _chunks(txt: str, size: int) -> Iterable[str]:
        for i in range(0, len(txt), size):
            yield txt[i : i + size]

    if len(text) <= CHUNK_SIZE:
        return _post(prompt_template.format(text=text))

    responses = []
    for part in _chunks(text, CHUNK_SIZE):
        prompt = prompt_template.format(text=part)
        responses.append(_post(prompt))

    combined = "".join(
        choice["message"]["content"]
        for resp in responses
        for choice in resp.get("choices", [])
    )
    return {"choices": [{"message": {"content": combined}}]}
