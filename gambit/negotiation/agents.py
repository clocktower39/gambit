"""Live MiniMax-M3 negotiation policies — the LLM side of the seam.

`LLMSeller` and `LLMBuyer` are drop-in implementations of the same `SellerPolicy` /
`BuyerCounterparty` protocols the deterministic `KnobSellerPolicy` / `HeuristicBuyer` satisfy,
so the existing `run_episode` referee can pit two M3 agents against each other or mix an LLM
side against a heuristic one — the referee never learns which is which (that's the seam).

Each side sees ONLY its own private information: the seller knows the secret floor (and must
never reveal or sell below it); the buyer knows its hidden budget (and is additionally bounded
by the `enforce_reservation` hard rail, so a silver-tongued seller can't talk it over budget).
We deliberately do NOT clamp the seller to the floor — a below-floor seller move is the very
integrity signal `audit_episode` exists to catch.

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


def _run_sync(coro):
    """Run an async coroutine to completion from sync code.

    `run_episode` is a sync referee, so we own the event loop here. If we're already inside a
    running loop (e.g. a notebook), `asyncio.run` would raise — fall back to a dedicated thread so
    the call still completes rather than crashing the episode."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


def _ask(agent, prompt: str, attempts: int = 5) -> AgentMove:
    """Get one structured move, retrying a FRESH call on M3's intermittent endpoint flakiness.

    M3 over the Anthropic-compat endpoint fails two transient ways: (1) it leaks native tool-call
    tokens as plain text, failing output validation (`UnexpectedModelBehavior`); and (2) it sometimes
    returns a response whose `content` is null, which pydantic_ai's Anthropic adapter then iterates —
    `TypeError: 'NoneType' object is not iterable`. Both clear on a clean retry, so we re-call a few
    times with a short backoff. `output_retries` only covers (1) within a conversation; this catches
    both with fresh calls before surfacing the failure honestly (never fabricate a move)."""
    import time as _time

    from pydantic_ai.exceptions import UnexpectedModelBehavior

    last: Exception | None = None
    for i in range(attempts):
        try:
            return _run_sync(agent.run(prompt)).output
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
    "move and nothing else."
)

_BUYER_SYSTEM = (
    "You are a marketplace buyer negotiating to buy one item, in character for your persona. You "
    "know your SECRET maximum budget and must NEVER reveal it and NEVER offer or accept above it. "
    "Let your style, eagerness, and patience shape how hard and how fast you push. Make exactly ONE "
    "move per turn. Walking away is a legitimate tactic — a first walk is a bluff to pressure the "
    "seller, not a final exit. Return strictly the structured move and nothing else."
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
        from pydantic_ai import Agent

        system = _SELLER_SYSTEM
        if self._lessons:
            # Promoted lessons are advisory tactics, appended so the integrity rails above stay primary.
            system += "\n\nLessons from past negotiations:\n" + "\n".join(f"- {x}" for x in self._lessons)
        # retries on output > 1: M3 occasionally emits a malformed tool-call instead of clean JSON;
        # an in-conversation re-prompt usually recovers, so we'd rather retry than fail an episode.
        return Agent(model_for("chat"), output_type=AgentMove, system_prompt=system, retries={"output": 3})

    @property
    def agent(self):
        if self._agent is None:
            self._agent = self._build_agent()
        return self._agent

    def _move(self, prompt: str, *, accept_price: float) -> Move:
        out = _ask(self.agent, prompt)
        # Integrity rail: an accept ALWAYS closes at the price ON THE TABLE, never one the model
        # self-names. Otherwise an LLM seller could emit action="accept", offer=list_price on turn 1
        # and close above the buyer's standing offer with no consent — uncaught reward inflation that
        # Tier-1 can't see (the accept's own price is "in the transcript"). Offers stay verbatim so the
        # below-floor audit still catches a cheating seller.
        offer = accept_price if out.action == "accept" else out.offer
        return Move(role="seller", text=out.text, action=out.action, offer=offer, reasoning=out.reasoning)

    def opening(self, item: Item) -> Move:
        prompt = (
            f"{item.public_blurb()}\n"
            f"Your SECRET floor (never reveal, never go below): ${item.floor_price:.0f}.\n"
            f"This is your OPENING move — the buyer has not spoken yet. Round 0 of {self.max_turns}.\n"
            "State your opening ask as a single move."
        )
        return self._move(prompt, accept_price=item.list_price)  # accept-on-open is degenerate; backstop only

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
        # An accept closes at the buyer's standing offer (never above our own ask), else our ask.
        accept_price = min(buyer_offer, current_ask) if buyer_offer is not None else current_ask
        return self._move(prompt, accept_price=accept_price)


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

        return Agent(model_for("buyer"), output_type=AgentMove, system_prompt=_BUYER_SYSTEM, retries={"output": 3})

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
