"""Gate #1 — prove MiniMax-M3 returns reliable STRUCTURED output through Pydantic AI.

This is the load-bearing pre-build spike: the whole typed-agent architecture rests on
`Agent(output_type=...)` working on M3's Anthropic-compatible endpoint.

Run:   uv run python scripts/spike_minimax.py
Needs: MINIMAX_API_KEY in .env  (MINIMAX_BASE_URL/MODEL default to the Anthropic endpoint).

Checks
  1. Raw connectivity via the anthropic SDK (the documented MiniMax pattern).
  2. Pydantic AI Agent(output_type=SellerMove) returns a schema-valid object N times (the real bet).
  3. Latency + token usage, so we can extrapolate per-generation cost.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from typing import Literal

from pydantic import BaseModel

from gambit.settings import settings


class SellerMove(BaseModel):
    """Stand-in for the real typed move — enough to exercise structured output."""

    reasoning: str = ""
    text: str
    action: Literal["offer", "accept", "walk"]
    offer: float | None = None


SYSTEM = "You are a sharp, friendly marketplace seller. Never reveal your secret floor."
PROMPT = (
    "You are selling a used mountain bike. List price $600, secret floor $450 (never go below it). "
    "The buyer just offered $400. Make exactly ONE negotiation move."
)


def check_raw() -> bool:
    from anthropic import Anthropic

    client = Anthropic(api_key=settings.minimax_api_key, base_url=settings.minimax_base_url)
    t0 = time.perf_counter()
    msg = client.messages.create(
        model=settings.minimax_model,
        max_tokens=300,
        system=SYSTEM,
        messages=[{"role": "user", "content": [{"type": "text", "text": PROMPT}]}],
    )
    dt = time.perf_counter() - t0
    text = "".join(b.text for b in msg.content if b.type == "text")
    print(f"[raw] ok in {dt:.2f}s · in={msg.usage.input_tokens} out={msg.usage.output_tokens}")
    print(f"[raw] text: {text[:140]!r}")
    return bool(text)


async def check_structured(n: int = 5) -> bool:
    from pydantic_ai import Agent

    from gambit.llm import model_for

    agent = Agent(model_for("chat"), output_type=SellerMove, system_prompt=SYSTEM)
    oks, lats = 0, []
    for i in range(n):
        t0 = time.perf_counter()
        try:
            result = await agent.run(PROMPT)
            dt = time.perf_counter() - t0
            lats.append(dt)
            mv = result.output
            assert isinstance(mv, SellerMove)
            # integrity smoke check: a valid move never offers below the floor
            below_floor = mv.offer is not None and mv.offer < 450 and mv.action != "walk"
            oks += 1
            flag = "  ⚠ below-floor!" if below_floor else ""
            print(f"[struct {i + 1}/{n}] ok {dt:.2f}s · action={mv.action} offer={mv.offer}{flag}")
        except Exception as e:  # noqa: BLE001 — spike wants to see any failure mode
            print(f"[struct {i + 1}/{n}] FAIL {type(e).__name__}: {e}")
    if lats:
        print(f"[struct] {oks}/{n} schema-valid · median {statistics.median(lats):.2f}s/call")
    return oks == n


def main() -> None:
    if not settings.minimax_api_key:
        print("MINIMAX_API_KEY not set — add it to .env and rerun.")
        return
    print(f"endpoint={settings.minimax_base_url}  model={settings.minimax_model}\n")
    raw = check_raw()
    print()
    structured = asyncio.run(check_structured())
    print("\n=== GATE #1 ===")
    print(f"  raw connectivity  : {'PASS' if raw else 'FAIL'}")
    print(f"  structured output : {'PASS' if structured else 'FAIL'}  (Pydantic AI output_type on M3)")
    print(
        "  → proceed with the typed-agent architecture."
        if raw and structured
        else "  → structured-output bet at risk; investigate before committing the rebuild."
    )


if __name__ == "__main__":
    main()
