"""MiniMax-M3 model factory for Pydantic AI, via the Anthropic-compatible endpoint.

The provider lives in exactly one place, so swapping the host (or pointing at the China
endpoint) is a one-line/.env change. Built once and cached.
"""

from __future__ import annotations

from functools import lru_cache

from gambit.settings import settings


@lru_cache(maxsize=1)
def _provider():
    from anthropic import AsyncAnthropic
    from pydantic_ai.providers.anthropic import AnthropicProvider

    # MiniMax speaks the Anthropic wire format at a custom base_url; pass a configured client.
    client = AsyncAnthropic(api_key=settings.minimax_api_key, base_url=settings.minimax_base_url)
    return AnthropicProvider(anthropic_client=client)


def model_for(role: str):
    """Return the Pydantic AI model for a role: 'chat' | 'buyer' | 'verifier'."""
    from pydantic_ai.models.anthropic import AnthropicModel

    name = {
        "chat": settings.minimax_model,
        "buyer": settings.minimax_model,
        "verifier": settings.verifier_model_id,
    }[role]
    return AnthropicModel(name, provider=_provider())
