#!/usr/bin/env python3
"""Play as the buyer while other buyers compete for the same listing.

This is a play harness, not the full MarketplaceDomain. It reuses the interactive
`scripts.play` seats and agents, but feeds the trained seller policy with
seller-visible portfolio state through `MarketplaceState.features_for_thread`.

Run:
    uv run python scripts/play_multiple.py
    uv run python scripts/play_multiple.py --buyers 3 --item 1 --show-thinking
"""

from __future__ import annotations

import argparse
import random
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logfire

from gambit.negotiation import (
    BuyerPersona,
    BuyerThreadState,
    Episode,
    Item,
    ListingState,
    MarketplaceState,
    Move,
    Outcome,
    PolicyStore,
    audit_episode,
    budget_of,
    reward,
    situation_key,
)
from gambit.settings import settings
from gambit import observability as obs
from scripts.play import (
    BuyerDeps,
    HumanBuyer,
    PACING_HORIZON,
    PERSONAS,
    UNCAPPED,
    _agent_move,
    _configure_logfire,
    _money,
    _pick_item,
    _print_catalog,
    _render,
    _safe_run,
    buyer_agent,
    load_policy,
    seller_agent,
    SellerDeps,
)

LISTING_ID = "listing"
HUMAN_THREAD_ID = "you"
OTHER_THREAD_PREFIX = "other"
HUMAN_PERSONA = BuyerPersona(name="You", style="human", budget_ratio=1.0)

_TRACED = False


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _finalize(
    item: Item,
    *,
    deal: bool,
    price: float | None,
    turns: int,
    walked_by: str | None = None,
    reason: str = "",
) -> Outcome:
    surplus = 0.0
    if deal and price is not None:
        surplus = _clip((price - item.floor_price) / max(item.list_price - item.floor_price, 1e-9))
    return Outcome(deal=deal, price=price, turns=turns, walked_by=walked_by, reason=reason, surplus=surplus)


class SharedMarket:
    """Thread-safe seller-visible marketplace state for this play harness."""

    def __init__(self, item: Item, buyer_count: int):
        threads = {
            HUMAN_THREAD_ID: BuyerThreadState(thread_id=HUMAN_THREAD_ID, listing_id=LISTING_ID),
        }
        for idx in range(buyer_count):
            tid = f"{OTHER_THREAD_PREFIX}-{idx + 1}"
            threads[tid] = BuyerThreadState(thread_id=tid, listing_id=LISTING_ID)

        self._lock = threading.RLock()
        self.state = MarketplaceState(
            listings={LISTING_ID: ListingState(listing_id=LISTING_ID, item=item)},
            threads=threads,
        )
        self.current_ask = item.list_price
        self.sold_event = threading.Event()
        self.sold_to: str | None = None
        self.sold_price: float | None = None

    def snapshot(self) -> tuple[MarketplaceState, float, str | None, float | None]:
        with self._lock:
            return self.state.model_copy(deep=True), self.current_ask, self.sold_to, self.sold_price

    def set_ask(self, ask: float) -> None:
        with self._lock:
            if self.sold_to is not None:
                return
            self.current_ask = ask

    def update_thread(self, thread_id: str, *, offer: float | None = None, status: str | None = None) -> bool:
        with self._lock:
            if self.sold_to is not None:
                return False
            thread = self.state.threads[thread_id]
            update: dict[str, object] = {}
            if offer is not None:
                update["current_offer"] = offer
            if status is not None:
                update["status"] = status
            self.state.threads[thread_id] = thread.model_copy(update=update)
            return True

    def commit_sale(self, thread_id: str, price: float) -> bool:
        with self._lock:
            if self.sold_to is not None:
                return False
            self.state = self.state.commit_sale(LISTING_ID, thread_id, price)
            self.sold_to = thread_id
            self.sold_price = price
            self.sold_event.set()
            return True

    def market_line_for_human(self) -> str:
        state, _, _, _ = self.snapshot()
        active = max(0, len(state.active_threads_for(LISTING_ID)) - 1)
        best = state.best_offer_for(LISTING_ID, exclude_thread_id=HUMAN_THREAD_ID)
        if best is None:
            return f"{active} other active buyer{'s' if active != 1 else ''}; no competing offers yet."
        return f"{active} other active buyer{'s' if active != 1 else ''}; competing offer exists."

    def market_line_for_seller(self) -> str:
        state, ask, _, _ = self.snapshot()
        active = max(0, len(state.active_threads_for(LISTING_ID)) - 1)
        best = state.best_offer_for(LISTING_ID, exclude_thread_id=HUMAN_THREAD_ID)
        if best is None:
            return f"{active} other active buyer{'s' if active != 1 else ''}; no competing offers yet."
        return f"{active} other active buyer{'s' if active != 1 else ''}; best competing offer {_money(best)} vs ask {_money(ask)}."


class MarketplaceSeller:
    """The trained seller policy, with portfolio-derived Features for the human thread."""

    name = "m3-marketplace-seller"

    def __init__(self, log: list[Move], max_turns: int, show_thinking: bool, policy: PolicyStore, market: SharedMarket):
        self.log = log
        self.max_turns = max_turns
        self.show_thinking = show_thinking
        self.policy = policy
        self.market = market

    def _deps(self, item: Item, current_ask: float, buyer_offer: float | None, round_idx: int) -> SellerDeps:
        state, _, _, _ = self.market.snapshot()
        features = state.features_for_thread(
            HUMAN_THREAD_ID,
            current_ask=current_ask,
            round_idx=round_idx,
            max_turns=self.max_turns,
        )
        return SellerDeps(
            item=item,
            current_ask=current_ask,
            buyer_offer=buyer_offer,
            round_idx=round_idx,
            max_rounds=self.max_turns,
            transcript=_render(self.log),
            knobs=self.policy.knobs.resolve(features),
            lessons=self.policy.promoted_lessons(situation_key(item)),
        )

    def _commit(self, mv: Move, *, span) -> Move:
        self.log.append(mv)
        span.set_attributes({"action": mv.action, "offer": mv.offer, "text": mv.text, "reasoning": mv.reasoning})
        obs.move(role=mv.role, action=mv.action, offer=mv.offer, text=mv.text, reasoning=mv.reasoning)
        label = "Seller"
        if mv.action == "offer" and mv.offer is not None:
            label = f"Seller · {_money(mv.offer)}"
        elif mv.action == "accept" and mv.offer is not None:
            label = f"Seller accepts {_money(mv.offer)}"
        elif mv.action == "walk":
            label = "Seller passes"
        print(f"{label}: {mv.text or f'({mv.action})'}")
        if self.show_thinking and mv.reasoning:
            print(f"  Reasoning: {mv.reasoning}")
        if mv.action == "offer" and mv.offer is not None:
            self.market.set_ask(mv.offer)
        return mv

    def opening(self, item: Item) -> Move:
        with logfire.span("marketplace seller opening") as span:
            deps = self._deps(item, item.list_price, None, 0)
            market_line = self.market.market_line_for_seller()
            task = (
                "Open the negotiation with your asking price as an 'offer'. "
                f"Seller-visible market context: {market_line}"
            )
            am = _safe_run(seller_agent, task, deps, "seller", typing_label="Seller")
            offer = am.offer if am.offer is not None else round(item.list_price * deps.knobs.opening_anchor_ratio)
            return self._commit(
                Move(role="seller", action="offer", offer=offer, text=am.text, reasoning=am.reasoning),
                span=span,
            )

    def respond(self, item: Item, current_ask: float, buyer_offer: float | None, round_idx: int) -> Move:
        with logfire.span("marketplace seller turn {round}", round=round_idx) as span:
            try:
                state, _, sold_to, _ = self.market.snapshot()
                if sold_to is not None:
                    return Move(role="seller", action="walk", text="Listing already sold.")
                features = state.features_for_thread(
                    HUMAN_THREAD_ID,
                    current_ask=current_ask,
                    round_idx=round_idx,
                    max_turns=self.max_turns,
                )
                deps = self._deps(item, current_ask, buyer_offer, round_idx)
            except (KeyError, ValueError) as exc:
                logfire.warn("seller turn skipped after market state changed: {err}", err=str(exc))
                return Move(role="seller", action="walk", text="Listing already sold.")
            best = state.best_offer_for(LISTING_ID, exclude_thread_id=HUMAN_THREAD_ID)
            market_context = (
                f"Seller-visible market context: {int(features.active_buyers)} other active buyer"
                f"{'s' if int(features.active_buyers) != 1 else ''}; "
                f"best competing offer {_money(best) if best is not None else 'none'}; "
                "do not reveal private buyer state."
            )
            am = _safe_run(
                seller_agent,
                f"Make your move. {market_context}",
                deps,
                "seller",
                typing_label="Seller",
            )
            if self.market.sold_event.is_set():
                return Move(role="seller", action="walk", text="Listing already sold.")
            return self._commit(_agent_move(am, "seller", buyer_offer, floor=item.floor_price), span=span)


class BackgroundBuyer(threading.Thread):
    """An LLM buyer negotiating privately against the shared standing ask."""

    def __init__(
        self,
        *,
        idx: int,
        item: Item,
        persona: BuyerPersona,
        market: SharedMarket,
        max_turns: int,
        show_thinking: bool,
        stop_event: threading.Event,
    ):
        super().__init__(name=f"buyer-{idx}", daemon=True)
        self.thread_id = f"{OTHER_THREAD_PREFIX}-{idx}"
        self.display_name = f"Other buyer {idx}"
        self.item = item
        self.persona = persona
        self.market = market
        self.max_turns = max_turns
        self.show_thinking = show_thinking
        self.stop_event = stop_event
        self.log: list[Move] = []
        self.current_offer: float | None = None
        self.walked_once = False

    def run(self) -> None:
        jitter = random.uniform(1.0, 3.0)
        if self.stop_event.wait(jitter):
            return
        for round_idx in range(1, self.max_turns + 1):
            if self.stop_event.is_set() or self.market.sold_event.is_set():
                return
            _, seller_ask, _, _ = self.market.snapshot()
            budget = budget_of(self.item, self.persona)
            with logfire.span("background buyer turn {buyer} · {round}", buyer=self.thread_id, round=round_idx):
                am = _safe_run(
                    buyer_agent,
                    "Make your move against the current standing seller ask.",
                    BuyerDeps(
                        item=self.item,
                        budget=budget,
                        seller_ask=seller_ask,
                        current_offer=self.current_offer,
                        round_idx=round_idx,
                        max_rounds=self.max_turns,
                        transcript=_render(self.log),
                    ),
                    self.thread_id,
                    typing_label=None,
                )
                mv = _agent_move(am, "buyer", seller_ask, budget=budget)

            if self.stop_event.is_set() or self.market.sold_event.is_set():
                return
            self.log.append(mv)

            if mv.action == "offer" and mv.offer is not None:
                self.current_offer = mv.offer
                if self.market.update_thread(self.thread_id, offer=mv.offer, status="active"):
                    print("\nMarket update: Another buyer made an offer.")
            elif mv.action == "accept" and mv.offer is not None:
                self.current_offer = mv.offer
                if self.market.update_thread(self.thread_id, offer=mv.offer):
                    try:
                        sold = self.market.commit_sale(self.thread_id, mv.offer)
                    except ValueError as exc:
                        logfire.warn("background buyer sale rejected: {err}", err=str(exc))
                        return
                    if sold:
                        print("\nMarket update: Another buyer accepted. The listing sold.")
                return
            elif mv.action == "walk":
                if self.walked_once:
                    self.market.update_thread(self.thread_id, status="walked")
                    return
                self.walked_once = True
                if not self.market.sold_event.is_set():
                    print(f"\nMarket update: Other buyer is threatening to pass.")

            if self.stop_event.wait(random.uniform(5.0, 9.0)):
                return

        if not self.stop_event.is_set() and not self.market.sold_event.is_set():
            self.market.update_thread(self.thread_id, status="closed")


def _build_episode(item: Item, moves: list[Move], outcome: Outcome) -> Episode:
    return Episode(item=item, persona=HUMAN_PERSONA, moves=moves, outcome=outcome)


def play_multiple(
    *,
    item: Item,
    policy: PolicyStore,
    policy_desc: str,
    buyer_count: int,
    turns: int | None,
    show_thinking: bool,
    save: bool,
) -> int:
    horizon = turns if turns is not None else PACING_HORIZON
    referee_turns = turns if turns is not None else UNCAPPED
    log: list[Move] = []
    market = SharedMarket(item, buyer_count)
    seller = MarketplaceSeller(log, horizon, show_thinking, policy, market)
    buyer = HumanBuyer(log, horizon, show_thinking)
    stop_event = threading.Event()

    background_buyers = [
        BackgroundBuyer(
            idx=i + 1,
            item=item,
            persona=PERSONAS[(i + 1) % len(PERSONAS)],
            market=market,
            max_turns=horizon,
            show_thinking=show_thinking,
            stop_event=stop_event,
        )
        for i in range(buyer_count)
    ]

    print(f"\n{item.name}")
    print("-" * max(len(item.name), 12))
    cap_note = f"{turns} turns max." if turns is not None else "No turn limit - deal, walk, or pass/Ctrl-D to leave."
    print(f"You are the buyer. {cap_note}")
    print(f"List: {_money(item.list_price)}")
    print(f"Agent: {policy_desc}")
    print(f"You are competing against {buyer_count} other buyer{'s' if buyer_count != 1 else ''}.")
    print("Market updates are real background-buyer moves generated by this harness.")
    print("Type naturally: ask, counter, accept, or pass. Ctrl-D also passes.\n")

    outcome: Outcome | None = None
    seller_ask = item.list_price
    buyer_offer: float | None = None
    seller_walked = False

    try:
        with obs.job("human-vs-agent", source="human", market="multi",
                     title=f"{item.name} — marketplace ({buyer_count} buyers)",
                     list_price=item.list_price, floor=item.floor_price,
                     background_buyers=buyer_count), \
             obs.episode(bucket=situation_key(item), seat="buyer"):
            opening = seller.opening(item)
            seller_ask = opening.offer or item.list_price
            market.set_ask(seller_ask)

            for worker in background_buyers:
                worker.start()

            for round_idx in range(1, referee_turns + 1):
                if market.sold_event.is_set():
                    _, _, sold_to, sold_price = market.snapshot()
                    outcome = _finalize(
                        item,
                        deal=False,
                        price=None,
                        turns=round_idx,
                        walked_by=None,
                        reason=f"sold to {sold_to}",
                    )
                    break

                print(f"\nMarket: {market.market_line_for_human()}")
                bmove = buyer.respond(item, seller_ask, round_idx, buyer_offer)
                logfire.info("human buyer move: {action} {offer}", action=bmove.action, offer=bmove.offer)
                if market.sold_event.is_set():
                    _, _, sold_to, sold_price = market.snapshot()
                    outcome = _finalize(
                        item,
                        deal=False,
                        price=None,
                        turns=round_idx,
                        reason=f"sold to {sold_to}",
                    )
                    break
                if bmove.action == "accept":
                    if market.commit_sale(HUMAN_THREAD_ID, bmove.offer or seller_ask):
                        outcome = _finalize(item, deal=True, price=bmove.offer, turns=round_idx, reason="buyer accepted")
                    else:
                        outcome = _finalize(item, deal=False, price=None, turns=round_idx, reason="listing already sold")
                    break
                if bmove.action == "walk":
                    market.update_thread(HUMAN_THREAD_ID, status="walked")
                    outcome = _finalize(
                        item,
                        deal=False,
                        price=None,
                        turns=round_idx,
                        walked_by="buyer",
                        reason="buyer passed",
                    )
                    break
                elif bmove.offer is not None:
                    buyer_offer = bmove.offer
                    market.update_thread(HUMAN_THREAD_ID, offer=bmove.offer, status="active")

                if market.sold_event.is_set():
                    _, _, sold_to, sold_price = market.snapshot()
                    outcome = _finalize(
                        item,
                        deal=False,
                        price=None,
                        turns=round_idx,
                        reason=f"sold to {sold_to}",
                    )
                    break

                smove = seller.respond(item, seller_ask, buyer_offer, round_idx)
                if market.sold_event.is_set():
                    _, _, sold_to, sold_price = market.snapshot()
                    outcome = _finalize(
                        item,
                        deal=False,
                        price=None,
                        turns=round_idx,
                        reason=f"sold to {sold_to}",
                    )
                    break
                if smove.action == "accept":
                    if market.commit_sale(HUMAN_THREAD_ID, smove.offer or buyer_offer or seller_ask):
                        outcome = _finalize(item, deal=True, price=smove.offer, turns=round_idx, reason="seller accepted")
                    else:
                        outcome = _finalize(item, deal=False, price=None, turns=round_idx, reason="listing already sold")
                    break
                if smove.action == "walk":
                    if seller_walked:
                        outcome = _finalize(
                            item,
                            deal=False,
                            price=None,
                            turns=round_idx,
                            walked_by="seller",
                            reason="seller re-confirmed walk",
                        )
                        break
                    seller_walked = True
                elif smove.offer is not None:
                    seller_ask = smove.offer
                    market.set_ask(seller_ask)

            outcome = outcome or _finalize(item, deal=False, price=None, turns=referee_turns, reason="timeout")
            _ep = _build_episode(item, log, outcome)
            obs.outcome(deal=outcome.deal, result=("deal" if outcome.deal else "no-deal"),
                        price=outcome.price, reward=reward(_ep), surplus=outcome.surplus,
                        viol=len(audit_episode(_ep)), turns=outcome.turns, bucket=situation_key(item))
    finally:
        stop_event.set()
        for worker in background_buyers:
            worker.join(timeout=1.0)

    ep = _build_episode(item, log, outcome)
    viol = audit_episode(ep)
    r = reward(ep)

    print("\nScorecard")
    print("-" * 60)
    if outcome.deal:
        turn_word = "turn" if outcome.turns == 1 else "turns"
        print(f"Deal: {_money(outcome.price)} in {outcome.turns} {turn_word}")
        print(f"Reward: {r:+.2f} · surplus {outcome.surplus:.2f}")
    else:
        print(f"No deal: {outcome.reason} after {outcome.turns} turns")
        print(f"Reward: {r:+.2f}")
    if viol:
        print(f"Audit: {len(viol)} violation(s): {'; '.join(viol)}")
    else:
        print("Audit: clean")
    if save:
        print("Saved: skipped - marketplace games need a portfolio episode schema before becoming proposer fuel.")
    print("Trace: Logfire captured the episode, turns, intent calls, and chat lines." if _TRACED else "Trace: set LOGFIRE_TOKEN in .env to walk the chat natively in Logfire.")
    return 0


def main() -> int:
    global _TRACED
    p = argparse.ArgumentParser(description="Negotiate by hand vs a trained seller with competing buyers")
    p.add_argument("--buyers", type=int, default=2, help="number of background competing buyers (default: 2)")
    p.add_argument("--checkpoint", default=None, help="PolicyStore JSON to load")
    p.add_argument("--item", default=None, help="item: index, name keyword, or omit for a random pick")
    p.add_argument("--list-items", action="store_true", help="print the catalog and exit")
    p.add_argument("--turns", type=int, default=None, help="hard turn cap")
    p.add_argument("--show-thinking", action="store_true", help="reveal agent private reasoning")
    p.add_argument("--trace-console", action="store_true", help="also print the Logfire span tree inline")
    p.add_argument("--no-save", action="store_true", help="suppress save reminder; marketplace games are not persisted yet")
    args = p.parse_args()

    if args.list_items:
        _print_catalog()
        return 0
    if args.buyers < 0:
        print("--buyers must be >= 0")
        return 1
    if not settings.minimax_api_key:
        print("MINIMAX_API_KEY not set - needed for the M3 agent. Add it to .env and rerun.")
        return 1

    item = _pick_item(args.item)
    policy, policy_desc = load_policy(args.checkpoint)
    _TRACED = _configure_logfire(args.trace_console)
    return play_multiple(
        item=item,
        policy=policy,
        policy_desc=policy_desc,
        buyer_count=args.buyers,
        turns=args.turns,
        show_thinking=args.show_thinking,
        save=not args.no_save,
    )


if __name__ == "__main__":
    raise SystemExit(main())
