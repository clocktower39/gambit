"""Gate #1 — prove MiniMax-M3 returns reliable STRUCTURED output through Pydantic AI.

This is the load-bearing pre-build spike: the whole typed-agent architecture rests on
`Agent(output_type=...)` working on M3's Anthropic-compatible endpoint.

Run:   uv run python scripts/spike_minimax.py
Needs: MINIMAX_API_KEY in .env  (MINIMAX_BASE_URL/MODEL default to the Anthropic endpoint).

Checks (base functionality, unchanged)
  1. Raw connectivity via the anthropic SDK (the documented MiniMax pattern).
  2. Pydantic AI Agent(output_type=SellerMove) returns a schema-valid object N times (the real bet).
  3. Latency + token usage, so we can extrapolate per-generation cost.
  4. Integrity smoke check: a valid move never offers/accepts below the secret floor.

The structured check (2–4) runs as a **pydantic-evals** `Dataset`: every scenario is a `Case`,
schema-validity / floor-respect are `Evaluator`s (assertions), latency is the native duration
column, and tokens/cost ride along as eval metrics. The whole run streams to the same Logfire
project as the improvement curve when `LOGFIRE_TOKEN` is set — one dashboard for spike + curve.
"""

from __future__ import annotations

import statistics
import time
from typing import Literal

from pydantic import BaseModel
from pydantic_evals import Case, Dataset, increment_eval_metric
from pydantic_evals.evaluators import Evaluator, EvaluatorContext, IsInstance

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))  # make `gambit` importable

from gambit.settings import settings


class SellerMove(BaseModel):
    """Stand-in for the real typed move — enough to exercise structured output."""

    reasoning: str = ""
    text: str
    action: Literal["offer", "accept", "walk"]
    offer: float | None = None


class Scenario(BaseModel):
    """One seller situation: the prompt the agent answers + the secret floor it must respect."""

    name: str
    prompt: str
    floor: float
    list_price: float


SYSTEM = "You are a sharp, friendly marketplace seller. Never reveal your secret floor."

# A small spread of situations (vs. the old single prompt × N) so structured output is
# exercised across margins; `repeat` below still gives N samples each for the schema bet.
SCENARIOS = [
    Scenario(
        name="mtn-bike",
        floor=450,
        list_price=600,
        prompt=(
            "You are selling a used mountain bike. List price $600, secret floor $450 "
            "(never go below it). The buyer just offered $400. Make exactly ONE negotiation move."
        ),
    ),
    Scenario(
        name="vintage-lens",
        floor=180,
        list_price=240,
        prompt=(
            "You are selling a vintage camera lens. List price $240, secret floor $180 "
            "(never go below it). The buyer opened at $150. Make exactly ONE negotiation move."
        ),
    ),
    Scenario(
        name="office-chair",
        floor=90,
        list_price=140,
        prompt=(
            "You are selling an ergonomic office chair. List price $140, secret floor $90 "
            "(never go below it). The buyer lowballed at $70. Make exactly ONE negotiation move."
        ),
    ),
]


class FloorRespected(Evaluator[Scenario, SellerMove]):
    """Integrity smoke check: a valid move never offers/accepts below the scenario's floor."""

    def evaluate(self, ctx: EvaluatorContext[Scenario, SellerMove]) -> bool:
        mv = ctx.output
        if mv.action == "walk" or mv.offer is None:
            return True
        return mv.offer >= ctx.inputs.floor


async def make_move(scenario: Scenario) -> SellerMove:
    """The task under eval: one structured seller move via Pydantic AI on MiniMax-M3.

    Records token usage as eval metrics so per-generation cost stays extrapolable (the report
    surfaces per-call means). Raises on any failure — pydantic-evals records it as a case error,
    which is exactly the schema-validity signal the gate reads."""
    from pydantic_ai import Agent

    from gambit.llm import model_for

    agent = Agent(model_for("chat"), output_type=SellerMove, system_prompt=SYSTEM)
    result = await agent.run(scenario.prompt)
    usage = result.usage()
    increment_eval_metric("input_tokens", usage.input_tokens or 0)
    increment_eval_metric("output_tokens", usage.output_tokens or 0)
    return result.output


def check_raw() -> bool:
    from anthropic import Anthropic

    client = Anthropic(api_key=settings.minimax_api_key, base_url=settings.minimax_base_url)
    t0 = time.perf_counter()
    msg = client.messages.create(
        model=settings.minimax_model,
        max_tokens=300,
        system=SYSTEM,
        messages=[{"role": "user", "content": [{"type": "text", "text": SCENARIOS[0].prompt}]}],
    )
    dt = time.perf_counter() - t0
    text = "".join(b.text for b in msg.content if b.type == "text")
    print(f"[raw] ok in {dt:.2f}s · in={msg.usage.input_tokens} out={msg.usage.output_tokens}")
    print(f"[raw] text: {text[:140]!r}")
    return bool(text)


def check_structured(repeat: int = 2) -> bool:
    """Run the structured-output bet as a pydantic-evals Dataset; print the report + return PASS/FAIL.

    `repeat` re-runs every scenario N times (the old "schema-valid N times" loop, now per-case),
    so total structured calls = len(SCENARIOS) × repeat."""
    dataset = Dataset(
        name="minimax-structured-output",
        cases=[Case(name=s.name, inputs=s) for s in SCENARIOS],
        evaluators=[IsInstance(type_name="SellerMove"), FloorRespected()],
    )
    report = dataset.evaluate_sync(make_move, repeat=repeat, max_concurrency=2)
    report.print(include_input=False, include_output=True, include_durations=True)

    # Derive the gate from per-case assertions: every call must be schema-valid (IsInstance) and
    # floor-respecting (FloorRespected). A task error shows up as a missing/failed assertion.
    cases = report.cases
    n = len(cases)
    schema_ok = sum(1 for c in cases if c.assertions.get("IsInstance") and c.assertions["IsInstance"].value)
    floor_ok = sum(1 for c in cases if c.assertions.get("FloorRespected") and c.assertions["FloorRespected"].value)
    below = [c.name for c in cases
             if c.assertions.get("FloorRespected") and not c.assertions["FloorRespected"].value]

    lats = [c.task_duration for c in cases if c.task_duration]
    in_tok = [c.metrics.get("input_tokens", 0) for c in cases]
    out_tok = [c.metrics.get("output_tokens", 0) for c in cases]
    if lats:
        print(f"[struct] {schema_ok}/{n} schema-valid · {floor_ok}/{n} floor-respecting · "
              f"median {statistics.median(lats):.2f}s/call")
    if any(in_tok) or any(out_tok):
        print(f"[struct] mean tokens/call: in={statistics.mean(in_tok):.0f} "
              f"out={statistics.mean(out_tok):.0f}  → multiply by calls/generation for the budget")
    if below:
        print(f"[struct] ⚠ below-floor moves in: {', '.join(below)}")
    return schema_ok == n and floor_ok == n


def main() -> None:
    if not settings.minimax_api_key:
        print("MINIMAX_API_KEY not set — add it to .env and rerun.")
        return

    if settings.logfire_token:  # stream the spike to the same dashboard as the curve, if configured
        import logfire

        logfire.configure(token=settings.logfire_token, service_name="gambit", console=False)
        logfire.instrument_pydantic_ai()

    print(f"endpoint={settings.minimax_base_url}  model={settings.minimax_model}\n")
    raw = check_raw()
    print()
    structured = check_structured()
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
