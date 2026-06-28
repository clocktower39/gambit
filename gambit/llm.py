"""MiniMax-M3 model factory for Pydantic AI, via the Anthropic-compatible endpoint.

The provider lives in exactly one place, so swapping the host (or pointing at the China
endpoint) is a one-line/.env change. The default provider is built once and cached; pass
`fresh=True` for a NON-shared client (each owns its own httpx pool), which is required when
running episodes concurrently — the cached AsyncAnthropic's pool is bound to the event loop it
was first used on, so sharing it across simultaneous loops/threads breaks.
"""

from __future__ import annotations

from functools import lru_cache

from gambit.settings import settings


def _build_provider():
    from anthropic import AsyncAnthropic
    from pydantic_ai.providers.anthropic import AnthropicProvider

    # MiniMax speaks the Anthropic wire format at a custom base_url; pass a configured client.
    client = AsyncAnthropic(api_key=settings.minimax_api_key, base_url=settings.minimax_base_url)
    return AnthropicProvider(anthropic_client=client)


@lru_cache(maxsize=1)
def _provider():
    return _build_provider()


def model_for(role: str, *, fresh: bool = False):
    """Return the Pydantic AI model for a role: 'chat' | 'buyer' | 'verifier'.

    `fresh=True` builds a dedicated provider/client (not the shared cache) — use it for agents
    that may run concurrently so each gets its own event-loop-safe connection pool."""
    from pydantic_ai.models.anthropic import AnthropicModel

    name = {
        "chat": settings.minimax_model,
        "buyer": settings.minimax_model,
        "verifier": settings.verifier_model_id,
    }[role]
    return AnthropicModel(name, provider=_build_provider() if fresh else _provider())
