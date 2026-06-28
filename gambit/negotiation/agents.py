"""Live MiniMax-M3 negotiation policies — the LLM side of the seam.

`LLMSeller` and `LLMBuyer` are drop-in implementations of the same `SellerPolicy` /
`BuyerCounterparty` protocols the deterministic `KnobSellerPolicy` / `HeuristicBuyer` satisfy,
so the existing `run_episode` referee can pit two M3 agents against each other or mix an LLM
side against a heuristic one — the referee never learns which is which (that's the seam).

Each side sees ONLY its own private information: the seller knows the secret floor (and must
never reveal or sell below it); the buyer knows its hidden budget (and is additionally bounded
by the `enforce_reservation` hard rail, so a silver-tongued seller can't talk it over budget).
The seller carries the symmetric rail (architecture.md, the four-agents table): a floor-aware
`output_validator` raises `ModelRetry` on any below-floor offer/accept so the model self-corrects
(re-price or walk) instead of cheating, and `_move` refuses a below-floor *accept* (the table price
can be under the floor even when the model didn't name a number) by holding the line. `audit_episode`
remains the deterministic backstop that measures any breach that still slips through.

`run_episode` is synchronous but `Agent.run` is async, so these policies bridge async→sync via
`asyncio.run` per move. That makes them safe to call from a sync top-level (the live runner) but
NOT from inside a running event loop without the thread fallback below.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import BaseModel

from gambit.llm import model_for

from .models import BuyerPersona, Item, Move, budget_of
from .policies import enforce_reservation


class AgentMove(BaseModel):
    """The typed move we ask M3 for. Agents only act — they never just 'talk' — so the action set
    is the three terminal-or-progress tactics; `reasoning` is the private scratchpad, `text` is the
    line the opponent actually hears. `offer` is the price for an offer/accept (None for a walk)."""

    reasoning: str = ""
    text: str
    action: Literal["offer", "accept", "walk"]
    offer: float | None = None


import threading

_THREAD_LOOP = threading.local()


def _run_sync(coro):
    """Run an async coroutine to completion from sync code, reusing ONE persistent event loop per
    thread (NOT a fresh loop per call).

    `run_episode` is a sync referee that calls Agent.run once per move. `asyncio.run` per call
    creates and *destroys* an event loop every move; the AsyncAnthropic httpx connections are bound
    to that loop, so on teardown they (a) flood stderr with 'Event loop is closed' / 'no running
    event loop' errors and (b) get discarded — forcing a brand-new TCP+TLS connection on the next
    move. Over a long, concurrent (ThreadPool) run that is both noisy and slow. A persistent
    per-thread loop keeps the connection pool alive across moves and the teardown quiet. Each worker
    thread gets its own loop, so concurrency stays safe (paired with the per-instance client)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = getattr(_THREAD_LOOP, "loop", None)
        if loop is None or loop.is_closed():
            loop = asyncio.new_event_loop()
            _THREAD_LOOP.loop = loop
        return loop.run_until_complete(coro)
    # Already inside a running loop (e.g. a notebook) → isolate the work in a worker thread, which
    # has no running loop of its own and so takes the persistent-loop path above.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: _run_sync(coro)).result()


_SELLER_TEMP = 0.2   # low temperature: cut sampling variance so paired A/B comparisons are less noisy
_MAX_TOKENS = 512    # cap output per move: the structured move is short, so this just stops the model
                     # from writing long pitches/reasoning — the dominant per-call latency at scale


def _ask(agent, prompt: str, attempts: int = 5, deps=None) -> AgentMove:
    """Get one structured move, retrying a FRESH call on M3's intermittent endpoint flakiness.

    M3 over the Anthropic-compat endpoint fails two transient ways: (1) it leaks native tool-call
    tokens as plain text, failing output validation (`UnexpectedModelBehavior`); and (2) it sometimes
    returns a response whose `content` is null, which pydantic_ai's Anthropic adapter then iterates —
    `TypeError: 'NoneType' object is not iterable`. Both clear on a clean retry, so we re-call a few
    times with a short backoff. `output_retries` only covers (1) within a conversation; this catches
    both with fresh calls before surfacing the failure honestly (never fabricate a move). `deps` carries
    per-run context to the agent's output validator (the seller passes its secret floor)."""
    import time as _time

    from pydantic_ai.exceptions import UnexpectedModelBehavior

    last: Exception | None = None
    for i in range(attempts):
        try:
            return _run_sync(agent.run(prompt, deps=deps)).output
        except (UnexpectedModelBehavior, TypeError) as e:
            last = e
            _time.sleep(0.4 * (i + 1))      # brief backoff for transient endpoint hiccups / rate blips
    raise last  # type: ignore[misc]


def _price(x: float | None) -> str:
    return f"${x:.0f}" if x is not None else "none yet"


_SELLER_SYSTEM = (
    "You are a sharp, friendly marketplace seller negotiating the sale of one item. You drive a "
    "good price while staying warm and credible. You know your SECRET floor — the lowest price you "
    "will ever take — and you must NEVER reveal it and NEVER offer or accept below it. Make exactly "
    "ONE move per turn. Walking away is a legitimate tactic: a first walk is a pressure threat, not "
    "the end, so use it to test a stubborn buyer when it serves you. Return strictly the structured "
    "move and nothing else. Be terse and fast: keep `reasoning` to one short clause and `text` to "
    "ONE or two short sentences — no long pitches."
)

_BUYER_SYSTEM = (
    "You are a marketplace buyer negotiating to buy one item, in character for your persona. You "
    "know your SECRET maximum budget and must NEVER reveal it and NEVER offer or accept above it. "
    "Let your style, eagerness, and patience shape how hard and how fast you push. Make exactly ONE "
    "move per turn. Walking away is a legitimate tactic — a first walk is a bluff to pressure the "
    "seller, not a final exit. Return strictly the structured move and nothing else. Be terse and "
    "fast: keep `reasoning` to one short clause and `text` to ONE or two short sentences."
)


class LLMSeller:
    """A live M3 seller. Implements `SellerPolicy`: knows the floor, makes one structured move.

    `lessons` are per-bucket tactical hints (promoted by the offline loop) injected into the system
    prompt; empty by default. The pydantic-ai `Agent` is built once per instance and reused."""

    def __init__(self, name: str = "llm", lessons: list[str] | None = None, max_turns: int = 6):
        self.name = name
        self.max_turns = max_turns
        self._lessons = lessons or []
        self._agent = None  # lazily built so construction stays cheap / offline-safe

    def _build_agent(self):
        from pydantic_ai import Agent, ModelRetry, RunContext

        system = _SELLER_SYSTEM
        if self._lessons:
            # Promoted lessons are advisory tactics, appended so the integrity rails above stay primary.
            system += "\n\nLessons from past negotiations:\n" + "\n".join(f"- {x}" for x in self._lessons)
        # deps_type=float carries the secret floor to the output validator; low temperature cuts
        # variance; retries cover M3's occasional malformed tool-call AND the validator's ModelRetry.
        agent = Agent(model_for("chat", fresh=True), output_type=AgentMove, deps_type=float, system_prompt=system,
                      model_settings={"temperature": _SELLER_TEMP, "max_tokens": _MAX_TOKENS}, retries={"output": 4})

        @agent.output_validator
        def _floor_rail(ctx: RunContext[float], out: AgentMove) -> AgentMove:
            # Integrity rail (architecture.md): the seller may NEVER offer/accept below its floor.
            # Reject a model-named below-floor price → ModelRetry, so it re-prices or walks rather than cheat.
            floor = ctx.deps
            if out.action in ("offer", "accept") and out.offer is not None and out.offer < floor - 1e-6:
                raise ModelRetry(
                    f"Your move would {out.action} at ${out.offer:.0f}, BELOW your secret floor ${floor:.0f}. "
                    f"Never go below the floor. Counter at or above ${floor:.0f}, or walk away."
                )
            return out

        return agent

    @property
    def agent(self):
        if self._agent is None:
            self._agent = self._build_agent()
        return self._agent

    def _move(self, prompt: str, *, floor: float, accept_price: float, hold_price: float) -> Move:
        out = _ask(self.agent, prompt, deps=floor)
        if out.action == "accept":
            # An accept ALWAYS closes at the price ON THE TABLE, never one the model self-names (that
            # would be uncaught reward inflation Tier-1 can't see). And if that table price is below the
            # floor, REFUSE the accept and hold the line — the seller must not close below the wall even
            # when the model didn't name a sub-floor number.
            if accept_price < floor - 1e-6:
                return Move(role="seller", action="offer", offer=hold_price,
                            text="That's below what I can do — I'll hold here for now.",
                            reasoning="floor rail: refused a below-floor accept")
            return Move(role="seller", action="accept", offer=accept_price, text=out.text, reasoning=out.reasoning)
        # offer / walk pass through (the output validator already kept any offer at/above floor).
        return Move(role="seller", action=out.action, offer=out.offer, text=out.text, reasoning=out.reasoning)

    def opening(self, item: Item) -> Move:
        prompt = (
            f"{item.public_blurb()}\n"
            f"Your SECRET floor (never reveal, never go below): ${item.floor_price:.0f}.\n"
            f"This is your OPENING move — the buyer has not spoken yet. Round 0 of {self.max_turns}.\n"
            "State your opening ask as a single move."
        )
        # accept-on-open is degenerate; list_price is a safe backstop for both accept and hold.
        return self._move(prompt, floor=item.floor_price, accept_price=item.list_price, hold_price=item.list_price)

    def respond(self, item: Item, current_ask: float, buyer_offer: float | None, round_idx: int) -> Move:
        prompt = (
            f"{item.public_blurb()}\n"
            f"Your SECRET floor (never reveal, never go below): ${item.floor_price:.0f}.\n"
            "Negotiation state:\n"
            f"- Your current standing ask: ${current_ask:.0f}\n"
            f"- Buyer's latest offer: {_price(buyer_offer)}\n"
            f"- Round {round_idx} of {self.max_turns}.\n"
            "Respond with a single move (offer a new ask, accept, or walk)."
        )
        # An accept closes at the buyer's standing offer (never above our own ask), else our ask;
        # hold at the current ask (above floor) if the model tries to accept below the floor.
        accept_price = min(buyer_offer, current_ask) if buyer_offer is not None else current_ask
        return self._move(prompt, floor=item.floor_price, accept_price=accept_price, hold_price=current_ask)


class LLMBuyer:
    """A live M3 buyer. Implements `BuyerCounterparty` (`family='llm'`): knows its hidden budget,
    plays in persona, and every move passes through `enforce_reservation` as the hard budget rail."""

    family = "llm"

    def __init__(self, persona: BuyerPersona):
        self.persona = persona
        self._agent = None

    def budget(self, item: Item) -> int:
        return budget_of(item, self.persona)

    def _build_agent(self):
        from pydantic_ai import Agent

        return Agent(model_for("buyer", fresh=True), output_type=AgentMove, system_prompt=_BUYER_SYSTEM,
                     model_settings={"temperature": _SELLER_TEMP, "max_tokens": _MAX_TOKENS}, retries={"output": 3})

    @property
    def agent(self):
        if self._agent is None:
            self._agent = self._build_agent()
        return self._agent

    def respond(self, item: Item, seller_ask: float, round_idx: int, current_offer: float | None) -> Move:
        p, budget = self.persona, self.budget(item)
        prompt = (
            f"{item.public_blurb()}\n"
            f"You are {p.name}. Style: {p.style or 'pragmatic'}. "
            f"Eagerness: {p.eagerness:.2f} (0=cool, 1=keen). Patience: {p.patience} rounds.\n"
            f"Your SECRET maximum budget (never reveal, never exceed): ${budget:.0f}.\n"
            "Negotiation state:\n"
            f"- Seller's current ask: ${seller_ask:.0f}\n"
            f"- Your latest offer: {_price(current_offer)}\n"
            f"- Round {round_idx} of patience {p.patience}.\n"
            "Respond with a single move (offer a price, accept, or walk)."
        )
        out = _ask(self.agent, prompt)
        # An accept always means "yes at the seller's ask" — bind to it, never a model-named price
        # (enforce_reservation below still caps it at the hidden budget). Offers stay verbatim.
        offer = float(seller_ask) if out.action == "accept" else out.offer
        move = Move(role="buyer", text=out.text, action=out.action, offer=offer, reasoning=out.reasoning)
        # Hard rail on EVERY buyer move: the LLM can never offer/accept above its hidden budget.
        return enforce_reservation(move, budget)


if __name__ == "__main__":
    # Live smoke: real M3 calls. Two M3 agents negotiate, then an M3 seller vs a deterministic buyer.
    import time

    from .models import BuyerPersona, Item
    from .policies import HeuristicBuyer

    if __import__("gambit.settings", fromlist=["settings"]).settings.minimax_api_key == "":
        print("MINIMAX_API_KEY not set — add it to .env and rerun.")
        raise SystemExit(0)

    from .domain import run_episode

    item = Item(
        name="vintage road bike",
        description="lightweight steel frame, recently serviced",
        condition="Used - good",
        list_price=600,
        target_price=520,
        floor_price=450,
    )
    persona = BuyerPersona(name="Dana", style="frugal but decisive", budget_ratio=0.85, patience=5, eagerness=0.4)

    print("=== M3 seller vs M3 buyer ===")
    t0 = time.perf_counter()
    ep = run_episode(item, LLMSeller(), LLMBuyer(persona))
    dt = time.perf_counter() - t0
    print(ep.transcript())
    print(f"\noutcome: {ep.outcome}")
    print(f"(elapsed {dt:.1f}s, {len(ep.moves)} moves → ~{dt / max(len(ep.moves), 1):.1f}s/move)\n")

    print("=== M3 seller vs deterministic HeuristicBuyer ===")
    t0 = time.perf_counter()
    ep2 = run_episode(item, LLMSeller(), HeuristicBuyer(persona))
    dt = time.perf_counter() - t0
    print(ep2.transcript())
    print(f"\noutcome: {ep2.outcome}")
    print(f"(elapsed {dt:.1f}s)")
