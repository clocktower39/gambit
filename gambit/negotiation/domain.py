"""The negotiation referee, exposed to the engine as a `Domain`.

`rollout` runs ONE deterministic episode (the seed *generates* the scenario; the deterministic
policies have no randomness) and scores it with the verifiable reward. The referee owns
per-episode state (`current_ask`/`current_offer`) and is a *referee only* — it never knows
whether a side is a heuristic, a human, or an LLM. That's the seam.
"""

from __future__ import annotations

import random

from ..engine.seam import EpisodeResult
from .models import Episode, Item, Outcome, budget_of, situation_key
from .policy import PolicyStore
from .policies import BuyerCounterparty, KnobSellerPolicy, SellerPolicy
from .reward import audit_episode, reward

_PRICE_JITTER = (0.80, 1.20)   # per-seed price level spread (cosmetic — reward is scale-invariant)
_MARGIN_RANGE = (0.08, 0.55)   # per-seed margin (floor vs list): spans thin..fat, the strategic axis


def _scenario(base: Item, seed: int) -> Item:
    """Deterministically generate ONE distinct scenario from a base archetype + seed.

    A seed is NOT a bare item index: it perturbs the price level and — load-bearing — the MARGIN
    (floor relative to list). Margin is what actually moves the surplus landscape; reward is
    scale-invariant, so jittering price alone would be a no-op. Because the strategic shape is a
    function of the seed, DISJOINT seed sets yield DISJOINT scenarios — that is what makes a locked
    seed split a real held-out rather than a cosmetic one. Fully determined by `seed`, so the same
    seed always reproduces the same scenario and paired A/B stays valid."""
    rng = random.Random(seed)
    list_price = round(base.list_price * rng.uniform(*_PRICE_JITTER))
    floor = round(list_price * (1.0 - rng.uniform(*_MARGIN_RANGE)))
    target = round(floor + (list_price - floor) * rng.uniform(0.40, 0.85))
    return Item(name=base.name, description=base.description, condition=base.condition,
                list_price=list_price, target_price=target, floor_price=floor)


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _finalize(item: Item, budget: float, *, deal: bool, price: float | None, turns: int,
              walked_by: str | None = None, reason: str = "") -> Outcome:
    surplus = skill = 0.0
    if deal and price is not None:
        surplus = _clip((price - item.floor_price) / max(item.list_price - item.floor_price, 1e-9))
        if budget > item.floor_price:
            skill = _clip((price - item.floor_price) / max(budget - item.floor_price, 1e-9))
    return Outcome(deal=deal, price=price, turns=turns, walked_by=walked_by,
                   reason=reason, surplus=surplus, skill=skill)


def run_episode(item: Item, seller: SellerPolicy, buyer: BuyerCounterparty,
                max_turns: int = 6) -> Episode:
    """Pure referee over two policies → terminal Episode. Domain-specific turn-taking only.

    A walk is NON-TERMINAL (docs/strategy.md §4.1): the *first* walk by a side is a threat, not
    the end — the other side gets one rebuttal turn (the standing offer is preserved, so it can be
    accepted or bridged). No-deal is reached only when a side walks a *second* time (re-confirmed)
    or the turn budget runs out. A walk that instantly ended the episode would make every walk
    'real' and the single richest tactic in negotiation unlearnable. The honest-bluff integrity
    check (a staged mutual walk that resolves into a cozy split = collusion) needs intent and is a
    Tier-2 / live-verifier concern (`buyer_in_character`, slice 5), not a deterministic Tier-1 rail."""
    persona = buyer.persona
    budget = budget_of(item, persona)
    ep = Episode(item=item, persona=persona)

    opening = seller.opening(item)
    ep.moves.append(opening)
    seller_ask = opening.offer or item.list_price
    buyer_offer: float | None = None
    walked: set[str] = set()           # sides that have already walked once (a second walk is terminal)

    outcome: Outcome | None = None
    for r in range(1, max_turns + 1):
        bmove = buyer.respond(item, seller_ask, r, buyer_offer)
        ep.moves.append(bmove)
        if bmove.action == "accept":
            outcome = _finalize(item, budget, deal=True, price=bmove.offer, turns=r, reason="buyer accepted")
            break
        if bmove.action == "walk":
            if "buyer" in walked:                          # re-confirmed → real no-deal
                outcome = _finalize(item, budget, deal=False, price=None, turns=r,
                                    walked_by="buyer", reason="buyer re-confirmed walk")
                break
            walked.add("buyer")                            # soft walk: keep the standing offer; seller rebuts below
        elif bmove.offer is not None:
            buyer_offer = bmove.offer

        smove = seller.respond(item, seller_ask, buyer_offer, r)
        ep.moves.append(smove)
        if smove.action == "accept":
            outcome = _finalize(item, budget, deal=True, price=smove.offer, turns=r, reason="seller accepted")
            break
        if smove.action == "walk":
            if "seller" in walked:                         # re-confirmed → real no-deal
                outcome = _finalize(item, budget, deal=False, price=None, turns=r,
                                    walked_by="seller", reason="seller re-confirmed walk")
                break
            walked.add("seller")                           # soft walk: keep the standing ask; buyer rebuts next round
        elif smove.offer is not None:
            seller_ask = smove.offer

    ep.outcome = outcome or _finalize(item, budget, deal=False, price=None, turns=max_turns, reason="timeout")
    return ep


class NegotiationDomain:
    """The negotiation plug-in. Implements the engine `Domain` over a fixed item pool."""

    def __init__(self, items: list[Item], max_turns: int = 6):
        if not items:
            raise ValueError("NegotiationDomain needs at least one item")
        self.items = items
        self.max_turns = max_turns

    def scenario(self, seed: int) -> Item:
        """The deterministic scenario this seed generates (exposed so tests can assert that the
        train and locked seed sets cover genuinely disjoint scenarios, not the same items)."""
        return _scenario(self.items[seed % len(self.items)], seed)

    def rollout(self, policy: PolicyStore, counterparty: BuyerCounterparty, seed: int) -> EpisodeResult:
        item = self.scenario(seed)                         # seed GENERATES the scenario, deterministically
        seller = KnobSellerPolicy(policy.knobs, max_turns=self.max_turns)       # global parametric → per-turn
        ep = run_episode(item, seller, counterparty, self.max_turns)
        o = ep.outcome
        return EpisodeResult(
            bucket=situation_key(item),                    # buyer_type stays "unknown" until belief inference
            reward=reward(ep),
            viol=len(audit_episode(ep)),
            seed=seed,
            skill=(o.skill if (o and o.deal) else None),
        )
