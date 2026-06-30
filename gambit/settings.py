"""Typed runtime configuration (pydantic-settings), validated at import.

MiniMax-M3 is reached over its **Anthropic-compatible** endpoint, so base_url/model default to
the international MiniMax Anthropic endpoint and the wiring lives in gambit/llm.py.
"""

from __future__ import annotations

import secrets

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    # --- MiniMax-M3 (Anthropic-compatible endpoint) — the inner-loop LLM ---
    minimax_api_key: str = Field("", alias="MINIMAX_API_KEY")
    minimax_base_url: str = Field("https://api.minimax.io/anthropic", alias="MINIMAX_BASE_URL")
    minimax_model: str = Field("MiniMax-M3", alias="MINIMAX_MODEL")
    verifier_model: str = Field("", alias="VERIFIER_MODEL")   # Tier-2 audit; falls back to minimax_model
    offline: bool = Field(False, alias="OFFLINE")

    # --- observability / data ---
    logfire_token: str = Field("", alias="LOGFIRE_TOKEN")
    database_url: str = Field("", alias="DATABASE_URL")       # blank → in-memory store

    # --- optimizer backend: "local" (MiniMax, default) | "antigravity" (Gemini) ---
    optimizer_backend: str = Field("local", alias="OPTIMIZER_BACKEND")
    gemini_api_key: str = Field("", alias="GEMINI_API_KEY")

    # --- Voice buyer seat: LiveKit transport + Gemini Live; blank → typed/text seat only ---
    livekit_url: str = Field("", alias="LIVEKIT_URL")
    livekit_api_key: str = Field("", alias="LIVEKIT_API_KEY")
    livekit_api_secret: str = Field("", alias="LIVEKIT_API_SECRET")

    # --- Admin dashboard (HTTP Basic Auth; creds live ONLY in .env) ---
    # Format: "user:pass,user2:pass2". Blank → admin endpoints return 503 (feature off).
    admin_users: str = Field("", alias="ADMIN_USERS")

    @field_validator("offline", mode="before")
    @classmethod
    def _blank_is_false(cls, v):
        # an empty `OFFLINE=` line in .env should mean "not set" → False, not a parse error
        return False if isinstance(v, str) and v.strip() == "" else v

    def llm_available(self) -> bool:
        """True when we can and should call the hosted LLM."""
        return bool(self.minimax_api_key) and not self.offline

    def voice_available(self) -> bool:
        """True when the voice seat can run: LiveKit transport + Gemini ears/mouth all configured."""
        return bool(self.livekit_url and self.livekit_api_key and self.livekit_api_secret
                    and self.gemini_api_key)

    def admin_credentials(self) -> dict[str, str]:
        """Parse ADMIN_USERS ('user:pass,user2:pass2') into {user: password}. Malformed entries skipped."""
        out: dict[str, str] = {}
        for pair in self.admin_users.split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            user, _, pw = pair.partition(":")
            user = user.strip()
            if user:
                out[user] = pw
        return out

    def admin_available(self) -> bool:
        """True when at least one admin credential is configured."""
        return bool(self.admin_credentials())

    def check_admin(self, user: str, password: str) -> bool:
        """Constant-time check of a (user, password) against the configured admin credentials."""
        expected = self.admin_credentials().get(user)
        if expected is None:
            return False
        return secrets.compare_digest(expected, password)

    @property
    def verifier_model_id(self) -> str:
        return self.verifier_model or self.minimax_model


settings = Settings()
