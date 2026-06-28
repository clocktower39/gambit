"""MiniMax-M3 wired through Pydantic AI's NATIVE Anthropic model.

MiniMax ships an Anthropic-compatible endpoint, so we use Pydantic AI's `AnthropicModel`
(native Anthropic Messages wire format: thinking blocks, tool-use — which is how Pydantic AI
enforces `output_type`) pointed at MiniMax's `base_url`, *not* the OpenAI-compat shim.

The provider lives here only. Swapping MiniMax for real Anthropic — or any other
Anthropic-compatible host — is a one-line `base_url` change in settings.
"""

from __future__ import annotations

from functools import lru_cache

from anthropic import AsyncAnthropic
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from gambit.settings import settings


@lru_cache(maxsize=1)
def _provider() -> AnthropicProvider:
    # Build the Anthropic client ourselves so base_url is set the same way across SDK versions.
    client = AsyncAnthropic(api_key=settings.minimax_api_key, base_url=settings.minimax_base_url)
    return AnthropicProvider(anthropic_client=client)


def model_for(role: str = "chat") -> AnthropicModel:
    """Return the MiniMax model for a role: 'chat' (seller/optimizer), 'buyer', or 'verifier'."""
    name = settings.verifier_model or settings.minimax_model if role == "verifier" else settings.minimax_model
    return AnthropicModel(name, provider=_provider())
