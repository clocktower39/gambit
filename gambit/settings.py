"""Typed runtime config (pydantic-settings) — the rebuild target that replaces config.py.

Values only; the provider/client lives in llm.py. MiniMax-M3 is reached through its
Anthropic-compatible endpoint (native Anthropic wire format via Pydantic AI).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    minimax_api_key: str = Field("", alias="MINIMAX_API_KEY")
    minimax_base_url: str = Field("https://api.minimax.io/anthropic", alias="MINIMAX_BASE_URL")
    minimax_model: str = Field("MiniMax-M3", alias="MINIMAX_MODEL")
    # Tier-2 integrity verifier — ideally a different/stronger model; falls back to minimax_model.
    verifier_model: str = Field("", alias="VERIFIER_MODEL")
    # Force deterministic heuristics (no network) when set or when no key exists.
    offline: bool = Field(False, alias="OFFLINE")

    def llm_available(self) -> bool:
        """True when we can and should call the hosted LLM."""
        return bool(self.minimax_api_key) and not self.offline


settings = Settings()
