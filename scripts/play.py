#!/usr/bin/env python3
"""Negotiate by hand against the trained agent — the interactive, real-world seat.

You take one seat; the **M3 agent driven by its learned `PolicyStore`** plays the other. This is
the bridge to the real world: the same policy that improves in self-play is the one you haggle
here — load the latest checkpoint (or a specific generation) and you're negotiating against what
it actually learned (its resolved knobs + the promoted per-bucket lessons), not a blank prompt.

You just *talk* — free text. An M3 extractor reads your intent (offer / accept / walk / banter)
while the agent responds in character, so "that screen's cracked, I'll give you 380", "ayooo",
or "is it unlocked?" all work. Doctrine (docs/strategy.md §4.1): a walk-away is usually a bluff.

Visibility: the whole session is Logfire-instrumented — episode → each turn → the M3 model call —
so you can walk the entire chat natively, including the agent's hidden reasoning.

Run:
    uv run python scripts/play.py                              # you = BUYER vs the trained M3 seller
    uv run python scripts/play.py --checkpoint checkpoints/gen8.json   # a specific trained generation
    uv run python scripts/play.py --seat seller --item 1 --show-thinking

Policy: --checkpoint <path>, else checkpoints/latest.json if present, else the seeded cold-start
prior (docs/strategy.md). Needs MINIMAX_API_KEY; LOGFIRE_TOKEN for the walkable trace.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, model_validator

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `gambit` importable

import logfire
from pydantic_ai import Agent, ModelRetry, RunContext

from gambit.llm import model_for
from gambit.negotiation import (
    BuyerPersona,
    Features,
    Item,
    Knobs,
    Move,
    PolicyStore,
    audit_episode,
    budget_of,
    reward,
    situation_key,
)
from gambit.negotiation.domain import run_episode
from gambit.negotiation.fixtures import PERSONAS
from gambit.settings import settings

PACING_HORIZON = 10        # the agent's sense of tempo (turn_frac + the "Round N/M" prompt); NOT a hard cap
UNCAPPED = 200             # referee backstop when --turns is unset; a human ends the game long before this
CHECKPOINTS_DIR = Path("checkpoints")
DEFAULT_CHECKPOINT = CHECKPOINTS_DIR / "latest.json"      # the loop's pointer to its newest trained policy
HUMAN_EPISODES_DIR = Path("data/human_episodes")
_TRACE_CONSOLE = False

# A play-only marketplace (kept separate from gambit.negotiation.fixtures, which is the engine's
# training/eval distribution). Spread across thin / mid / fat margins so different situation buckets
# get exercised. floor is the secret wall: floor <= target <= list, floor < list.
CATALOG: list[Item] = [
    Item(name="iPhone 13 Pro 256GB", description="Graphite, unlocked, 89% battery, with box",
         condition="Used - Good", list_price=520, target_price=470, floor_price=400),       # mid
    Item(name="Herman Miller Aeron (Size B)", description="Fully loaded, no rips, smoke-free",
         condition="Used - Excellent", list_price=650, target_price=560, floor_price=300),   # fat
    Item(name="Specialized Allez road bike (54cm)", description="Shimano Sora, recent tune-up",
         condition="Used - Good", list_price=720, target_price=690, floor_price=650),         # thin
    Item(name="PlayStation 5 (disc)", description="Original controller, cables, boxed",
         condition="Used - Good", list_price=380, target_price=350, floor_price=300),         # mid
    Item(name="DJI Mini 3 drone", description="3 batteries, controller, Fly More combo",
         condition="Used - Like New", list_price=420, target_price=380, floor_price=300),     # mid
    Item(name="Fender CD-60S acoustic guitar", description="Solid spruce top, with gig bag",
         condition="Used - Good", list_price=280, target_price=240, floor_price=140),         # fat
    Item(name="Burton Custom snowboard + bindings", description="158cm, tuned, light base wear",
         condition="Used - Good", list_price=300, target_price=260, floor_price=150),         # fat
    Item(name="Autonomous SmartDesk (standing)", description="Electric dual-motor, 53x30 top",
         condition="Used - Good", list_price=340, target_price=300, floor_price=280),         # mid
    Item(name="Pentax K1000 film camera (50mm)", description="Fully working meter, clean glass",
         condition="Used - Working", list_price=190, target_price=165, floor_price=95),       # fat
    Item(name="Keychron Q1 mechanical keyboard", description="Gasket mount, hot-swap, extra caps",
         condition="Used - Like New", list_price=160, target_price=145, floor_price=130),     # mid
    Item(name="Apple Watch Series 8 (45mm)", description="GPS, midnight, two bands, boxed",
         condition="Used - Good", list_price=240, target_price=210, floor_price=170),         # mid
    Item(name="Patagonia Nano Puff jacket (M)", description="Black, no tears, barely worn",
         condition="Used - Excellent", list_price=120, target_price=100, floor_price=55),     # fat
]


def _money(value: float | int | None) -> str:
    """Human money formatting: whole dollars when whole, cents when cents matter."""
    if value is None:
        return ""
    amount = round(float(value), 2)
    if abs(amount - round(amount)) < 0.005:
        return f"${amount:,.0f}"
    return f"${amount:,.2f}"


def _delta_money(value: float | int) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{_money(abs(value))}"


@contextmanager
def _typing(label: str | None):
    """Transient inline typing indicator for sync model calls."""
    if not label or _TRACE_CONSOLE or not sys.stdout.isatty():
        yield
        return
    msg = f"{label} is typing..."
    sys.stdout.write(f"  {msg}")
    sys.stdout.flush()
    try:
        yield
    finally:
        sys.stdout.write("\r" + (" " * (len(msg) + 2)) + "\r")
        sys.stdout.flush()


# --- typed moves + free-text intent extraction --------------------------------------------

class AgentMove(BaseModel):
    """One structured move from the M3 agent, mapped to a domain `Move` with the seat's role."""

    reasoning: str = ""                                   # private scratchpad (hidden from opponent)
    text: str                                             # the public line
    action: Literal["offer", "accept", "walk"]
    offer: float | None = None

    @model_validator(mode="after")
    def _accept_needs_price(self):
        if self.action == "accept" and self.offer is None:
            raise ValueError("accept must name the agreed price")
        return self


class Utterance(BaseModel):
    """Structured intent extracted from a person's free-text negotiation message."""

    action: Literal["talk", "offer", "accept", "walk"]
    offer: float | None = None


class SellerDeps(BaseModel):
    item: Item
    current_ask: float
    buyer_offer: float | None
    round_idx: int
    max_rounds: int
    transcript: str
    knobs: Knobs                                          # resolved from the learned PolicyStore this turn
    lessons: list[str] = []                               # promoted per-bucket lessons (what it learned)


class BuyerDeps(BaseModel):
    item: Item
    budget: float                                         # the hidden reservation — never exceed it
    seller_ask: float
    current_offer: float | None
    round_idx: int
    max_rounds: int
    transcript: str


seller_agent = Agent(model_for("chat"), output_type=AgentMove, retries=2,
                     system_prompt=(
                         "You are a sharp, warm marketplace seller in a multi-turn negotiation. Close at "
                         "the highest price the buyer will truly pay, in reasonable time — and walk rather "
                         "than take a bad deal. Never sell below or reveal your secret floor. Anchor on "
                         "your target; hold price and add value before conceding; concede on a shrinking, "
                         "conditional ladder. A buyer's walk-away is usually a bluff — don't panic below "
                         "your floor; let them go or make ONE final conditional offer, then stop chasing. "
                         "Text like a real person in marketplace DMs: usually one short sentence, never "
                         "more than two. Vary your phrasing; no canned closers like 'let me know what "
                         "you're thinking' or 'what's your budget'. Do not end with a generic solicitation; "
                         "ask a specific question only when it helps. Dry humor is fine. No emoji unless it "
                         "genuinely fits. Never fabricate."))
buyer_agent = Agent(model_for("buyer"), output_type=AgentMove, retries=2,
                    system_prompt=(
                        "You are a shrewd, friendly buyer in a multi-turn negotiation. Pay as little as "
                        "possible and never go above or reveal your hidden max budget — walk rather than "
                        "overpay. Open below budget with a reason; concede slowly and conditionally; make "
                        "the seller justify every dollar. A credible walk-away is your strongest lever, "
                        "but don't bluff yourself into a deal you'd regret. Text like a real person in "
                        "marketplace DMs: usually one short sentence, never more than two. Vary your "
                        "phrasing; don't end with a generic solicitation or stock closer. Ask a specific "
                        "question only when it helps. Dry humor is fine. No emoji unless it genuinely fits. "
                        "Never fabricate."))
extract_agent = Agent(
    model_for("buyer"), output_type=Utterance,
    system_prompt=(
        "You convert ONE chat message from a person who is haggling into a structured intent.\n"
        "- 'offer': they state or clearly imply a price they will pay/take → set offer to that number.\n"
        "- 'accept': they agree to the price currently on the table → set offer to that table price.\n"
        "- 'walk': they are unconditionally quitting for good (NOT a conditional threat like "
        "'350 or I walk' — that is still talk/offer).\n"
        "- 'talk': anything else — greetings, questions, objections, threats, banter with no firm number.\n"
        "Never invent a price; only set offer when the person actually names or accepts one."))


@seller_agent.instructions
def _seller_ctx(ctx: RunContext[SellerDeps]) -> str:
    d, item, k = ctx.deps, ctx.deps.item, ctx.deps.knobs
    lines = [
        f"You are selling: {item.public_blurb()}",
        f"SECRET FLOOR {_money(item.floor_price)} — never offer or accept below it, never reveal it.",
        f"Target {_money(item.target_price)}; your standing ask is {_money(d.current_ask)}.",
    ]
    if d.buyer_offer is not None:
        lines.append(f"The buyer's latest offer is {_money(d.buyer_offer)}.")
    # The LEARNED numeric policy, as concrete guidance for this turn:
    lines.append(f"Your learned stance here: concede about {k.concession_rate:.0%} of the remaining gap "
                 f"(shrinking as it drags), accept at or above {_money(item.list_price * k.accept_ratio)}, "
                 f"hold firm ~{k.walkaway_patience} rounds before walking.")
    if d.lessons:  # the promoted per-bucket lessons — what it learned works in this situation
        lines.append("TACTICS YOU'VE LEARNED WORK HERE:\n" + "\n".join(f"- {l}" for l in d.lessons))
    if d.transcript:
        lines.append("Conversation so far:\n" + d.transcript)
    lines.append("Public reply style: brief marketplace DM, one or two sentences, no generic closer.")
    lines.append(f"Round {d.round_idx}/{d.max_rounds}. Make exactly ONE move: 'offer' (set offer to your "
                 "new asking price), 'accept' (set offer to the agreed price), or 'walk'.")
    return "\n".join(lines)


@seller_agent.output_validator
def _protect_floor(ctx: RunContext[SellerDeps], mv: AgentMove) -> AgentMove:
    floor = ctx.deps.item.floor_price
    if mv.action != "walk" and mv.offer is not None and mv.offer < floor:
        raise ModelRetry(f"{_money(mv.offer)} is below your secret floor {_money(floor)} — never go below it.")
    return mv


@buyer_agent.instructions
def _buyer_ctx(ctx: RunContext[BuyerDeps]) -> str:
    d, item = ctx.deps, ctx.deps.item
    lines = [
        f"You are buying: {item.public_blurb()}",
        f"YOUR HIDDEN MAX BUDGET is {_money(d.budget)} — never offer or accept above it, never reveal it.",
        f"The seller's current ask is {_money(d.seller_ask)}.",
    ]
    if d.current_offer is not None:
        lines.append(f"Your latest offer was {_money(d.current_offer)}.")
    if d.transcript:
        lines.append("Conversation so far:\n" + d.transcript)
    lines.append("Public reply style: brief marketplace DM, one or two sentences, no generic closer.")
    lines.append(f"Round {d.round_idx}/{d.max_rounds}. Make exactly ONE move: 'offer' (set offer to your "
                 "new bid), 'accept' (set offer to the seller's ask), or 'walk'.")
    return "\n".join(lines)


@buyer_agent.output_validator
def _respect_budget(ctx: RunContext[BuyerDeps], mv: AgentMove) -> AgentMove:
    budget = ctx.deps.budget
    if mv.action != "walk" and mv.offer is not None and mv.offer > budget:
        raise ModelRetry(f"{_money(mv.offer)} exceeds your hidden max budget {_money(budget)} — never exceed it.")
    return mv


# --- shared dialogue: rendered for agent context, printed, and traced ---------------------

def _line(mv: Move) -> str:
    price = f" ({_money(mv.offer)})" if mv.offer is not None else ""
    return f"{mv.role.title()}{price}: {mv.text or f'({mv.action})'}"


def _render(log: list[Move]) -> str:
    return "\n".join(_line(m) for m in log if m.text or m.action != "talk")


def _terminal_label(mv: Move) -> str:
    role = mv.role.title()
    if mv.action == "accept" and mv.offer is not None:
        return f"{role} accepts {_money(mv.offer)}"
    if mv.action == "offer" and mv.offer is not None:
        return f"{role} · {_money(mv.offer)}"
    if mv.action == "walk":
        return f"{role} passes"
    return role


def _terminal_text(mv: Move) -> str:
    if mv.text:
        return mv.text
    if mv.action == "accept" and mv.offer is not None:
        return f"Deal at {_money(mv.offer)}."
    if mv.action == "offer" and mv.offer is not None:
        return f"{_money(mv.offer)}."
    if mv.action == "walk":
        return "I'll pass."
    return f"({mv.action})"


class _Seat:
    """Common plumbing: a shared dialogue `log` + per-move terminal print + Logfire trace."""

    echo_moves = True

    def __init__(self, log: list[Move], max_turns: int, show_thinking: bool):
        self.log, self.max_turns, self.show_thinking = log, max_turns, show_thinking

    def _commit(self, mv: Move, *, span) -> Move:
        """Record one move everywhere: shared log, terminal, and the open turn span."""
        self.log.append(mv)
        span.set_attributes({"action": mv.action, "offer": mv.offer,
                             "text": mv.text, "reasoning": mv.reasoning})
        logfire.info("{line}", line=_line(mv))            # readable chat line, nested in the turn
        if self.echo_moves:
            print(f"{_terminal_label(mv)}: {_terminal_text(mv)}")
            if self.show_thinking and mv.reasoning:
                print(f"  Reasoning: {mv.reasoning}")
        return mv


def _safe_run(agent: Agent, task: str, deps, who: str, *, typing_label: str | None = None) -> AgentMove:
    """Run the agent, but never crash an interactive game on a model hiccup or a validator that
    won't satisfy within `retries` — degrade to a graceful walk instead."""
    try:
        with _typing(typing_label):
            return agent.run_sync(task, deps=deps).output
    except Exception as e:  # noqa: BLE001 — bounded; any failure becomes a clean forfeit
        logfire.warn("{who} agent error → walking: {err}", who=who, err=str(e))
        return AgentMove(action="walk", text="I'll have to pass on this one.",
                         reasoning=f"agent error: {type(e).__name__}: {e}")


def _agent_move(am: AgentMove, role: str, standing: float | None, *,
                floor: float | None = None, budget: float | None = None) -> Move:
    """Map an AgentMove to a domain Move. An 'accept' binds to the price the OTHER side actually put
    on the table (`standing`) — never a number the accepter names — so a deal can't close at a price
    the counterparty never offered. If the agent 'accepts' but names a *different* price it really
    meant a counter, so emit an offer. Floor/budget keep any accept legal."""
    if am.action == "accept":
        if standing is None:                                       # nothing on the table → treat as a counter/hold
            return Move(role=role, action="offer", offer=am.offer, text=am.text, reasoning=am.reasoning)
        if am.offer is not None and abs(am.offer - standing) > 1e-6:   # named its own number → a counter, not an accept
            return Move(role=role, action="offer", offer=am.offer, text=am.text, reasoning=am.reasoning)
        if floor is not None and standing < floor:                # seller can't accept below floor → hold at floor
            return Move(role=role, action="offer", offer=floor, text=am.text, reasoning=am.reasoning)
        if budget is not None and standing > budget:              # buyer can't accept above budget → hold at budget
            return Move(role=role, action="offer", offer=budget, text=am.text, reasoning=am.reasoning)
        return Move(role=role, action="accept", offer=standing, text=am.text, reasoning=am.reasoning)
    return Move(role=role, action=am.action, offer=am.offer, text=am.text, reasoning=am.reasoning)


# --- the four seats -----------------------------------------------------------------------

class LlmSeller(_Seat):
    """The trained agent in the seller's chair — driven by its learned PolicyStore."""

    name = "m3-seller"

    def __init__(self, log, max_turns, show_thinking, policy: PolicyStore):
        super().__init__(log, max_turns, show_thinking)
        self.policy = policy

    def _deps(self, item: Item, current_ask: float, buyer_offer: float | None, round_idx: int) -> SellerDeps:
        gap = (current_ask - buyer_offer) / item.list_price if buyer_offer else 0.0
        feats = Features(margin_ratio=item.margin_ratio, reservation_gap=gap,
                         turn_frac=round_idx / max(self.max_turns, 1))
        return SellerDeps(item=item, current_ask=current_ask, buyer_offer=buyer_offer,
                          round_idx=round_idx, max_rounds=self.max_turns, transcript=_render(self.log),
                          knobs=self.policy.knobs.resolve(feats),
                          lessons=self.policy.promoted_lessons(situation_key(item)))

    def opening(self, item: Item) -> Move:
        with logfire.span("seller opening") as span:
            deps = self._deps(item, item.list_price, None, 0)
            am = _safe_run(seller_agent, "Open the negotiation with your asking price as an 'offer'.",
                           deps, "seller", typing_label="Seller")
            offer = am.offer if am.offer is not None else round(item.list_price * deps.knobs.opening_anchor_ratio)
            return self._commit(Move(role="seller", action="offer", offer=offer,
                                     text=am.text, reasoning=am.reasoning), span=span)

    def respond(self, item: Item, current_ask: float, buyer_offer: float | None, round_idx: int) -> Move:
        with logfire.span("seller turn {round}", round=round_idx) as span:
            am = _safe_run(seller_agent, "Make your move.",
                           self._deps(item, current_ask, buyer_offer, round_idx), "seller",
                           typing_label="Seller")
            return self._commit(_agent_move(am, "seller", buyer_offer, floor=item.floor_price), span=span)


class LlmBuyer(_Seat):
    name = "m3-buyer"
    family = "m3-llm"

    def __init__(self, log, max_turns, show_thinking, persona: BuyerPersona):
        super().__init__(log, max_turns, show_thinking)
        self.persona = persona

    def respond(self, item: Item, seller_ask: float, round_idx: int, current_offer: float | None) -> Move:
        budget = budget_of(item, self.persona)
        with logfire.span("buyer turn {round}", round=round_idx) as span:
            am = _safe_run(buyer_agent, "Make your move.",
                           BuyerDeps(item=item, budget=budget, seller_ask=seller_ask,
                                     current_offer=current_offer, round_idx=round_idx,
                                     max_rounds=self.max_turns, transcript=_render(self.log)), "buyer",
                           typing_label="Buyer")
            return self._commit(_agent_move(am, "buyer", seller_ask, budget=budget), span=span)


def _ask(prompt: str) -> str | None:
    """Read one line of free text. None on EOF/Ctrl-C (→ the seat walks gracefully)."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def _extract(raw: str, role: str, standing: float | None) -> Utterance:
    """Turn a free-text message into a structured intent. A bare number skips the LLM; anything
    else ('sounds good', 'nah too steep, 350?', 'is it unlocked?') is read by the M3 extractor."""
    bare = raw.lstrip("$ ").rstrip().replace(",", "")
    try:
        amount = float(bare)
        if amount > 0:                       # a bare positive number is unambiguously an offer
            return Utterance(action="offer", offer=amount)
    except ValueError:
        pass
    table = (f"The price on the table right now is {_money(standing)}." if standing is not None
             else "No price is on the table yet.")
    try:
        with logfire.span("intent extraction", role=role, standing=standing):
            with _typing("Reading"):
                return extract_agent.run_sync(f"You are the {role}. {table}\nThe person said: {raw!r}").output
    except Exception as e:  # noqa: BLE001 — extraction must never crash the game; treat as banter
        logfire.warn("intent extraction error → treating as talk: {err}", err=str(e))
        return Utterance(action="talk")


def _human_move(raw: str, role: str, standing: float | None) -> Move:
    """The human's words become the move's `text`; the M3 extractor fills in action + price."""
    u = _extract(raw, role, standing)
    if u.action == "accept":
        # An accept binds to the price ON THE TABLE. If they named a *different* number, that's a
        # counter-offer, not an acceptance — otherwise a side could "accept" at a price the other
        # never agreed to (the referee closes at the accepting move's price, and the Tier-1 audit
        # can't catch it because that move injects the number into the transcript itself).
        if u.offer is not None and standing is not None and abs(u.offer - standing) > 0.005:
            return Move(role=role, action="offer", offer=float(u.offer), text=raw)
        price = standing if standing is not None else u.offer
        if price is None:
            return Move(role=role, action="talk", text=raw)         # nothing on the table to accept yet
        return Move(role=role, action="accept", offer=float(price), text=raw)
    if u.action == "offer" and u.offer is None:
        return Move(role=role, action="talk", text=raw)             # offer-ish but no number → keep talking
    return Move(role=role, action=u.action, offer=u.offer, text=raw)


class HumanSeller(_Seat):
    name = "you"
    echo_moves = False

    def opening(self, item: Item) -> Move:
        print("\nOpen with your asking price.")
        while True:
            raw = _ask("You > ")
            if raw is not None and not raw:
                continue
            with logfire.span("seller opening (human)") as span:
                if raw is None:                                     # EOF → just list at the asking price
                    mv = Move(role="seller", action="offer", offer=item.list_price,
                              text=f"Thanks for looking. I'm asking {_money(item.list_price)}.")
                else:
                    mv = _human_move(raw, "seller", None)
                    if mv.action != "offer" or mv.offer is None:    # no price named → open at list, keep your words
                        mv = Move(role="seller", action="offer", offer=item.list_price, text=raw)
                return self._commit(mv, span=span)

    def respond(self, item: Item, current_ask: float, buyer_offer: float | None, round_idx: int) -> Move:
        while True:
            raw = _ask("You > ")
            if raw is not None and not raw:
                continue
            with logfire.span("seller turn {round} (human)", round=round_idx) as span:
                if raw is None:
                    mv = Move(role="seller", action="walk", text="I'll pass. Thanks for your time.")
                else:
                    mv = _human_move(raw, "seller", buyer_offer)
                return self._commit(mv, span=span)


class HumanBuyer(_Seat):
    name = "you"
    family = "human"
    persona = BuyerPersona(name="You", style="human", budget_ratio=1.0)  # no enforced cap; you decide
    echo_moves = False

    def respond(self, item: Item, seller_ask: float, round_idx: int, current_offer: float | None) -> Move:
        while True:
            raw = _ask("You > ")
            if raw is not None and not raw:
                continue
            with logfire.span("buyer turn {round} (human)", round=round_idx) as span:
                if raw is None:
                    mv = Move(role="buyer", action="walk", text="I'm going to pass, thanks.")
                else:
                    mv = _human_move(raw, "buyer", seller_ask)
                return self._commit(mv, span=span)


# --- policy loading + the game ------------------------------------------------------------

def _newest_checkpoint() -> Path | None:
    """The most recently written checkpoint in checkpoints/ — so play auto-tracks whatever the
    training loop wrote, regardless of how it names the files. Ignores the latest.json pointer."""
    if not CHECKPOINTS_DIR.is_dir():
        return None
    files = [p for p in CHECKPOINTS_DIR.glob("*.json") if p.name != "latest.json"]
    return max(files, key=lambda p: p.stat().st_mtime, default=None)


def load_policy(path: str | None) -> tuple[PolicyStore, str]:
    """Load the agent the human will face. Explicit --checkpoint wins; otherwise auto-pick the
    newest trained checkpoint the loop wrote (checkpoints/latest.json pointer, else the newest
    file in checkpoints/); else fall back to the seeded prior. A checkpoint is just PolicyStore JSON."""
    if path:
        target = Path(path)
        if target.exists():
            return PolicyStore.model_validate_json(target.read_text()), f"checkpoint {target}"
        raise SystemExit(f"checkpoint not found: {path}")           # explicit path that isn't there → fail loud
    if DEFAULT_CHECKPOINT.exists():
        return PolicyStore.model_validate_json(DEFAULT_CHECKPOINT.read_text()), f"checkpoint {DEFAULT_CHECKPOINT} (latest)"
    newest = _newest_checkpoint()
    if newest:
        return PolicyStore.model_validate_json(newest.read_text()), f"checkpoint {newest} (newest)"
    return PolicyStore(), "seeded cold-start prior (no checkpoint yet — train one to face a stronger agent)"


def _configure_logfire(console: bool) -> bool:
    global _TRACE_CONSOLE
    _TRACE_CONSOLE = console
    # scrubbing OFF: our prompts say "secret floor"/"budget" — negotiation terms, not real
    # credentials — and Logfire's default redaction would hide the very chat we want to walk.
    console_opt = logfire.ConsoleOptions(span_style="indented") if console else False
    # inspect_arguments=False: we always pass explicit kwargs, and f-string introspection fails
    # under the script's sys.path shim (the noisy InspectArgumentsFailedWarning mid-game).
    if settings.logfire_token:
        logfire.configure(token=settings.logfire_token, service_name="gambit",
                          console=console_opt, scrubbing=False, inspect_arguments=False)
        logfire.instrument_pydantic_ai()
        return True
    logfire.configure(send_to_logfire=False, console=console_opt, scrubbing=False,
                      inspect_arguments=False)
    return False


_TRACED = False


def _record_episode(ep, *, seat: str, policy_desc: str, reward_val: float,
                    viol: list[str], item: Item) -> Path | None:
    """Persist a real human-vs-agent game as a scored `Episode` (proposer fuel) AND emit it as its
    own tagged Logfire trace, so real interactions are a reviewable stream — not just self-play.

    Real games are valid scored data because WE own the seller's floor, so the deterministic surplus
    reward + Tier-1 audit hold (eval-plan §0). Tagged `source=human` so the optimizer can weight/segment
    it apart from self-play — as PROPOSER fuel, never straight into the deterministic promotion gate
    (humans aren't paired/reproducible; that would confound the A/B and invite poisoning)."""
    o = ep.outcome
    bucket = situation_key(item)
    result = "deal" if o.deal else "no-deal"
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record = {
        "source": "human", "ts": ts, "seat": seat, "policy": policy_desc, "bucket": bucket,
        "reward": reward_val, "surplus": o.surplus, "skill": o.skill,
        "viol": len(viol), "violations": viol,
        "deal": o.deal, "price": o.price, "turns": o.turns, "reason": o.reason,
        "episode": ep.model_dump(mode="json"),
    }
    path = None
    try:
        HUMAN_EPISODES_DIR.mkdir(parents=True, exist_ok=True)
        slug = "".join(c if c.isalnum() else "-" for c in item.name).strip("-").lower()[:32]
        stamp = ts.replace(":", "").replace("-", "")
        path = HUMAN_EPISODES_DIR / f"{stamp}-{slug}-{seat}-{uuid.uuid4().hex[:6]}.json"
        path.write_text(json.dumps(record, indent=2))
    except Exception as e:  # noqa: BLE001 — never crash a finished game on a write error
        logfire.warn("could not save human episode: {err}", err=str(e))
    # A standalone, filterable trace marking this real interaction as a learning datapoint.
    with logfire.span("human episode · {bucket} · {result}", kind="human_episode", source="human",
                      bucket=bucket, result=result, seat=seat, policy=policy_desc,
                      reward=reward_val, surplus=o.surplus, skill=o.skill, viol=len(viol),
                      deal=o.deal, price=o.price, turns=o.turns,
                      path=str(path) if path else None, transcript=ep.transcript()):
        pass
    return path


def play(seat: str, item: Item, persona: BuyerPersona, policy: PolicyStore, policy_desc: str,
         turns: int | None, show_thinking: bool, save: bool = True) -> int:
    # The game ends when someone deals or walks — the human can always pass/Ctrl-D. `horizon` is only
    # the agent's sense of tempo (turn_frac + the prompt); the referee runs to a high backstop, not 10.
    horizon = turns if turns is not None else PACING_HORIZON
    referee_turns = turns if turns is not None else UNCAPPED

    log: list[Move] = []
    if seat == "buyer":
        seller = LlmSeller(log, horizon, show_thinking, policy)
        buyer = HumanBuyer(log, horizon, show_thinking)
        matchup = "you (buyer) vs the trained seller"
    else:
        seller = HumanSeller(log, horizon, show_thinking)
        buyer = LlmBuyer(log, horizon, show_thinking, persona)
        budget_tag = f" [hidden budget {_money(budget_of(item, persona))}]" if show_thinking else ""
        matchup = f"you (seller) vs {buyer.name}{budget_tag}"

    print(f"\n{item.name}")
    print("─" * max(len(item.name), 12))
    cap_note = f"{turns} turns max." if turns is not None else "No turn limit — deal, walk, or pass/Ctrl-D to leave."
    print(f"You are the {seat}. {cap_note}")
    if seat == "seller":
        print(f"List: {_money(item.list_price)} · your floor: {_money(item.floor_price)}")
    else:
        print(f"List: {_money(item.list_price)}")
    print(f"Agent: {policy_desc}")
    if seat == "buyer" and show_thinking:  # show the trained stance you're up against
        k = policy.knobs.resolve(Features(margin_ratio=item.margin_ratio))
        lessons = policy.promoted_lessons(situation_key(item))
        print(f"Stance: open ~{_money(item.list_price * k.opening_anchor_ratio)}, "
              f"concede ~{k.concession_rate:.0%}, accept >= {_money(item.list_price * k.accept_ratio)}, "
              f"patience {k.walkaway_patience}" + (f", {len(lessons)} learned lesson(s)" if lessons else ""))
    print("Type naturally: ask, counter, accept, or pass. Ctrl-D also passes.\n")

    with logfire.span("negotiation: {item} — {matchup}", item=item.name, matchup=matchup,
                      seat=seat, source="human-vs-agent", policy=policy_desc,
                      list_price=item.list_price, floor=item.floor_price):
        ep = run_episode(item, seller, buyer, max_turns=referee_turns)
        o = ep.outcome
        viol = audit_episode(ep)
        r = reward(ep)
        logfire.info("outcome: {result}", result=("deal" if o.deal else "no deal"),
                     deal=o.deal, price=o.price, turns=o.turns, reward=r,
                     surplus=o.surplus, skill=o.skill, viol=len(viol), bucket=situation_key(item))

    saved = _record_episode(ep, seat=seat, policy_desc=policy_desc, reward_val=r,
                            viol=viol, item=item) if save else None

    print("\nScorecard")
    print("─" * 60)
    if o.deal:
        turn_word = "turn" if o.turns == 1 else "turns"
        print(f"Deal: {_money(o.price)} in {o.turns} {turn_word}")
        print(f"Reward: {r:+.2f} · surplus {o.surplus:.2f} · skill {o.skill:.2f}")
        if seat == "seller":
            print(f"Your edge: {_delta_money((o.price or 0) - item.floor_price)} over floor")
    else:
        print(f"No deal: {o.reason} after {o.turns} turns")
        print(f"Reward: {r:+.2f}")
    if viol:
        print(f"Audit: {len(viol)} violation(s): {'; '.join(viol)}")
    else:
        print("Audit: clean")
    if saved:
        print(f"Saved: {saved}  (source=human — proposer fuel + its own 'human_episode' Logfire trace)")
    print("Trace: Logfire captured the episode, turns, intent calls, and chat lines."
          if _TRACED else "Trace: set LOGFIRE_TOKEN in .env to walk the chat natively in Logfire.")
    return 0


def _pick_item(spec: str | None) -> Item:
    """Choose the item: an index, a name keyword, or (default) a random one from the catalog."""
    if spec is None:
        return random.choice(CATALOG)
    if spec.isdigit():
        return CATALOG[int(spec) % len(CATALOG)]
    matches = [it for it in CATALOG if spec.lower() in it.name.lower()]
    if not matches:
        raise SystemExit(f"no catalog item matches {spec!r} — try --list-items")
    return matches[0]


def _print_catalog() -> None:
    print("Catalog (use --item <index|name>):")
    for i, it in enumerate(CATALOG):
        print(f"  [{i:>2}] {it.name} — list {_money(it.list_price)}  ({it.condition}; {situation_key(it)})")


def main() -> int:
    global _TRACED
    p = argparse.ArgumentParser(description="Negotiate by hand vs the trained M3 agent")
    p.add_argument("--seat", choices=["buyer", "seller"], default="buyer",
                   help="which seat YOU take (default: buyer — you haggle the trained seller)")
    p.add_argument("--checkpoint", default=None,
                   help="PolicyStore JSON to load (default: checkpoints/latest.json, else seeded prior)")
    p.add_argument("--item", default=None,
                   help="item: index, name keyword, or omit for a random pick (see --list-items)")
    p.add_argument("--list-items", action="store_true", help="print the catalog and exit")
    p.add_argument("--persona", default="Fence-sitter Fran",
                   help="the M3 buyer's hidden persona (only when --seat seller)")
    p.add_argument("--turns", type=int, default=None,
                   help="hard turn cap (default: none — the game ends on a deal or a walk)")
    p.add_argument("--show-thinking", action="store_true", help="reveal the agent's private reasoning")
    p.add_argument("--trace-console", action="store_true",
                   help="also print the Logfire span tree inline in the terminal")
    p.add_argument("--no-save", action="store_true",
                   help="don't persist this game as a human episode (throwaway / testing)")
    args = p.parse_args()

    if args.list_items:
        _print_catalog()
        return 0

    if not settings.minimax_api_key:
        print("MINIMAX_API_KEY not set — needed for the M3 agent. Add it to .env and rerun.")
        return 1

    item = _pick_item(args.item)
    persona = next((p_ for p_ in PERSONAS if p_.name == args.persona), PERSONAS[1])
    policy, policy_desc = load_policy(args.checkpoint)
    _TRACED = _configure_logfire(args.trace_console)
    return play(args.seat, item, persona, policy, policy_desc, args.turns, args.show_thinking,
                save=not args.no_save)


if __name__ == "__main__":
    raise SystemExit(main())
