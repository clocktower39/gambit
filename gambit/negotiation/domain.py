"""The negotiation referee, exposed to the engine as a `Domain`.

`rollout` runs ONE deterministic episode (seed picks the scenario; the deterministic
policies have no randomness) and scores it with the verifiable reward. The referee owns
per-episode state (`current_ask`/`current_offer`) and is a *referee only* — it never knows
whether a side is a heuristic, a human, or an LLM. That's the seam.
"""

from __future__ import annotations

from ..engine.seam import EpisodeResult
from .models import Episode, Item, Outcome, budget_of, situation_key
from .policies import BuyerCounterparty, SellerPolicy
from .reward import audit_episode, reward


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
    """Pure referee over two policies → terminal Episode. Domain-specific turn-taking only."""
    persona = buyer.persona
    budget = budget_of(item, persona)
    ep = Episode(item=item, persona=persona)

    opening = seller.opening(item)
    ep.moves.append(opening)
    seller_ask = opening.offer or item.list_price
    buyer_offer: float | None = None

    outcome: Outcome | None = None
    for r in range(1, max_turns + 1):
        bmove = buyer.respond(item, seller_ask, r, buyer_offer)
        ep.moves.append(bmove)
        if bmove.action == "accept":
            outcome = _finalize(item, budget, deal=True, price=bmove.offer, turns=r, reason="buyer accepted")
            break
        if bmove.action == "walk":
            outcome = _finalize(item, budget, deal=False, price=None, turns=r,
                                walked_by="buyer", reason="buyer walked")
            break
        buyer_offer = bmove.offer

        smove = seller.respond(item, seller_ask, buyer_offer, r)
        ep.moves.append(smove)
        if smove.action == "accept":
            outcome = _finalize(item, budget, deal=True, price=smove.offer, turns=r, reason="seller accepted")
            break
        if smove.action == "walk":
            outcome = _finalize(item, budget, deal=False, price=None, turns=r,
                                walked_by="seller", reason="seller walked")
            break
        if smove.offer is not None:
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

    def rollout(self, policy: SellerPolicy, counterparty: BuyerCounterparty, seed: int) -> EpisodeResult:
        item = self.items[seed % len(self.items)]          # seed selects the scenario, deterministically
        ep = run_episode(item, policy, counterparty, self.max_turns)
        o = ep.outcome
        return EpisodeResult(
            bucket=situation_key(item),                    # buyer_type stays "unknown" until belief inference
            reward=reward(ep),
            viol=len(audit_episode(ep)),
            seed=seed,
            skill=(o.skill if (o and o.deal) else None),
        )
