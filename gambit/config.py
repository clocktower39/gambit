"""Runtime configuration, loaded from environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv is optional at runtime
    pass


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    base_url: str = os.getenv("DO_INFERENCE_BASE_URL", "https://inference.do-ai.run/v1/")
    api_key: str = os.getenv("DIGITAL_OCEAN_MODEL_ACCESS_KEY", "")
    chat_model: str = os.getenv("CHAT_MODEL", "llama3.3-70b-instruct")
    buyer_model: str = os.getenv("BUYER_MODEL", "llama3.3-70b-instruct")
    # Force deterministic heuristics (no network) when OFFLINE is set or no key exists.
    offline: bool = _truthy(os.getenv("OFFLINE"))


settings = Settings()


def llm_available() -> bool:
    """True when we can and should call the hosted LLM."""
    return bool(settings.api_key) and not settings.offline
