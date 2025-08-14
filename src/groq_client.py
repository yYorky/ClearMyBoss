"""Simple Groq API client for grammar suggestions."""
from __future__ import annotations

from typing import Any, Dict

import time
import requests
from requests.exceptions import HTTPError, RequestException

from config import settings

# Updated base URL to match Groq's OpenAI-compatible endpoint
GROQ_API_URL = "https://api.groq.com/openai/v1/completions"
PROMPT_TEMPLATE = "Review the following text for grammar and style:\n\n{text}"


def get_suggestions(
    text: str,
    prompt_template: str = PROMPT_TEMPLATE,
    *,
    retries: int = 3,
    backoff: float = 1.0,
) -> Dict[str, Any]:
    """Send ``text`` to Groq API and return the JSON response.

    Parameters
    ----------
    text:
        The text to review.
    prompt_template:
        Template used to build the prompt sent to Groq.
    retries:
        Number of times to retry on errors.
    backoff:
        Seconds to wait between retries; doubles after each attempt.
    """
    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
    payload = {"prompt": prompt_template.format(text=text)}

    for attempt in range(1, retries + 1):
        try:
            response = requests.post(
                GROQ_API_URL, json=payload, headers=headers, timeout=30
            )
            response.raise_for_status()
            return response.json()
        except HTTPError as exc:  # Retry on 5xx responses
            status = exc.response.status_code if exc.response else None
            if status and 500 <= status < 600 and attempt < retries:
                time.sleep(backoff)
                backoff *= 2
            else:
                raise
        except RequestException:
            if attempt < retries:
                time.sleep(backoff)
                backoff *= 2
            else:
                raise
