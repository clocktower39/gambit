"""Thin wrapper over the DigitalOcean Serverless Inference endpoint.

OpenAI-compatible, so we use the OpenAI SDK and just point base_url at DO.
All callers degrade gracefully to offline heuristics when no key is present.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from .config import settings


@lru_cache(maxsize=1)
def _client():
    from openai import OpenAI

    return OpenAI(base_url=settings.base_url, api_key=settings.api_key)


def chat(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 512,
) -> str:
    """Single chat completion -> assistant text."""
    resp = _client().chat.completions.create(
        model=model or settings.chat_model,
        messages=messages,
        temperature=temperature,
        max_completion_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()


def _extract_json(text: str) -> dict[str, Any]:
    """Tolerant JSON extraction — models sometimes wrap JSON in prose or fences."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text).rstrip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Grab the first balanced-looking {...} block.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Could not parse JSON from model output: {text[:200]!r}")


def chat_json(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 512,
) -> dict[str, Any]:
    """Chat completion that must return a JSON object."""
    raw = chat(messages, model=model, temperature=temperature, max_tokens=max_tokens)
    return _extract_json(raw)
