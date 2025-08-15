"""Simple Groq API client for text review suggestions."""
from __future__ import annotations

from typing import Any, Dict, Iterable

import logging
import time
import threading
import random
from collections import deque
import requests
from requests.exceptions import HTTPError, RequestException

from config import settings

logger = logging.getLogger(__name__)

# Groq's OpenAI-compatible endpoint for chat completions
# https://console.groq.com/docs shows that the API mirrors OpenAI's
# `/chat/completions` route rather than the legacy `/completions` path.
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
# Prompt sent with each request
# PROMPT_TEMPLATE = (
#     "Review the following text and provide suggestions for improvement. "
#     "Feel free to ask clarifying questions or offer broader comments beyond grammar. "
#     "Respond in one or two short sentences in plain language.\n\n{text}"
# )
PROMPT_TEMPLATE = (
    "Review the following text and provide a quick comment as if tagging it inside the doc. "
    "Feel free to ask clarifying questions. "
    "Refer to the exact sentence or phrase you are commenting on (not 'this text' or 'this part'). "
    "Be direct, concise, and helpful — 1–2 sentences max.\n\n{text}"
)


# System instruction to keep the model's feedback brief and relevant
# SYSTEM_PROMPT = (
#     "You are a no-nonsense boss reviewing your employee's work. "
#     "Provide direct, actionable feedback or clarifying questions in casual, plain language. "
#     "You may comment on broader issues beyond grammar. Keep feedback to one or two short sentences."
# )
SYSTEM_PROMPT = (
    "You are a sharp, no-nonsense boss reviewing a document directly in writing. "
    "Speak like you're leaving a quick comment inside the doc, pointing to the exact words, sentence, or section. "
    "Be specific: refer to text naturally, e.g., 'In the third paragraph...' or 'Where you say X...'. "
    "Feel free to ask clarifying questions or offer broader comments when helpful. "
    "Keep it short (1–2 sentences), plain, and human. "
    "Vary your phrasing — don't repeat the same opener each time. "
    "Call out unclear ideas, awkward wording, or anything that could be stronger. "
    "No fluff, no corporate jargon — just straight, useful feedback."
)

# Maximum bytes of text per request. Default tested at 20KB. Can be overridden via
# ``GROQ_CHUNK_SIZE`` environment variable.
CHUNK_SIZE = settings.GROQ_CHUNK_SIZE


class RateLimiter:
    """Sliding-window rate limiter.

    Tracks timestamps of the most recent ``requests_per_minute`` calls and
    ensures that no more than that number occur in any rolling 60 second
    window. If the limit would be exceeded, ``acquire`` blocks until enough
    time has passed for the oldest call to expire from the window. Thread-safe
    so multiple threads can share the limiter.
    """

    def __init__(self, requests_per_minute: int) -> None:
        self.max_calls = max(1, requests_per_minute)
        self.lock = threading.Lock()
        self.calls: deque[float] = deque()

    def acquire(self) -> None:
        """Block until another call is allowed.

        In addition to enforcing the sliding window, ensure that each call is
        spaced at least ``60 / max_calls`` seconds from the previous one. This
        smooths out bursts so that the upstream service isn't hit with many
        back-to-back requests that could trigger rate limits.
        """

        min_interval = 60 / self.max_calls
        while True:
            with self.lock:
                now = time.time()
                # Remove timestamps outside the 60 second window
                while self.calls and now - self.calls[0] >= 60:
                    self.calls.popleft()

                if len(self.calls) < self.max_calls and (
                    not self.calls or now - self.calls[-1] >= min_interval
                ):
                    self.calls.append(now)
                    return

                # Only apply the 60-second sliding window wait if we've already
                # reached the maximum number of calls for the window. When below
                # the limit we only need to enforce the minimum spacing between
                # consecutive calls.
                wait_window = (
                    self.calls[0] + 60 - now
                    if len(self.calls) >= self.max_calls
                    else 0
                )
                wait_spacing = (
                    self.calls[-1] + min_interval - now if self.calls else 0
                )
                wait = max(wait_window, wait_spacing)

            if wait > 0:
                time.sleep(wait)


rate_limiter = RateLimiter(settings.GROQ_REQUESTS_PER_MINUTE)

def get_suggestions(
    text: str,
    prompt_template: str = PROMPT_TEMPLATE,
    *,
    retries: int = 3,
    backoff: float = 1.0,
    halt_on_429: bool = True,
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
        try:
            responses.append(_post(prompt))
        except HTTPError as exc:
            status = exc.response.status_code if exc.response else None
            if status == 429 and halt_on_429:
                logger.error(
                    "Persistent 429 from Groq. Halting further requests for this document."
                )
                raise
            raise

    combined = "".join(
        choice["message"]["content"]
        for resp in responses
        for choice in resp.get("choices", [])
    )
    return {"choices": [{"message": {"content": combined}}]}
