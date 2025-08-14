"""Simple Groq API client for grammar suggestions."""
from __future__ import annotations

from typing import Any, Dict

import time
import requests
from requests.exceptions import HTTPError, RequestException

from config import settings

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
PROMPT_TEMPLATE = "Review the following text for grammar and style:\n\n{text}"

def get_suggestions(
    text: str,
    prompt_template: str = PROMPT_TEMPLATE,
    *,
    retries: int = 3,
    backoff: float = 1.0,
) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {settings.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = prompt_template.format(text=text)

    payload = {
        # Use a current model:
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": "You are a document reviewer and editor."},
            {"role": "user", "content": prompt},
        ],
        # Keep completions modest; oversized requests can 400 with context errors.
        "temperature": 0.2,
        "max_tokens": 800,
    }

    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(GROQ_API_URL, json=payload, headers=headers, timeout=30)
            # If it's a 4xx/5xx, capture the body so we can see why.
            if resp.status_code >= 400:
                try:
                    detail = resp.json()
                except Exception:
                    detail = {"text": resp.text}
                resp.raise_for_status()  # will raise HTTPError
            return resp.json()

        except HTTPError as exc:
            # Log details to your logger before deciding to retry
            status = exc.response.status_code if exc.response else None
            try:
                err_body = exc.response.json()  # often contains 'error' or 'message'
            except Exception:
                err_body = {"text": getattr(exc.response, "text", "")}
            # Example: logger.error("Groq  error %s: %s", status, err_body)

            # Only retry on 5xx; 400s are client-side (bad payload/model/etc.)
            if status and 500 <= status < 600 and attempt < retries:
                time.sleep(backoff); backoff *= 2
            else:
                raise

        except RequestException as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(backoff); backoff *= 2
            else:
                raise last_exc
