"""Simple Groq API client for grammar suggestions."""
from __future__ import annotations

from typing import Any, Dict

import requests

from config import settings

GROQ_API_URL = "https://api.groq.com/v1/completions"
PROMPT_TEMPLATE = "Review the following text for grammar and style:\n\n{text}"


def get_suggestions(text: str, prompt_template: str = PROMPT_TEMPLATE) -> Dict[str, Any]:
    """Send ``text`` to Groq API and return the JSON response."""
    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
    payload = {"prompt": prompt_template.format(text=text)}
    response = requests.post(GROQ_API_URL, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()
