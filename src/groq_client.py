"""Simple Groq API client for grammar suggestions."""
from __future__ import annotations

from typing import Any, Dict, Iterable

import time
import requests
from requests.exceptions import HTTPError, RequestException

from config import settings

# Groq's OpenAI-compatible endpoint for chat completions
# https://console.groq.com/docs shows that the API mirrors OpenAI's
# `/chat/completions` route rather than the legacy `/completions` path.
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
PROMPT_TEMPLATE = "Review the following text for grammar and style:\n\n{text}"
CHUNK_SIZE = 8 * 1024  # 8KB, keep requests comfortably under Groq limits

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
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 800,
        }

        last_exc = None
        _backoff = backoff
        for attempt in range(1, retries + 1):
            try:
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
                if status and 500 <= status < 600 and attempt < retries:
                    time.sleep(_backoff)
                    _backoff *= 2
                else:
                    raise

            except RequestException as exc:
                last_exc = exc
                if attempt < retries:
                    time.sleep(_backoff)
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
