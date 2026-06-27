"""Runs a single negotiation episode: seller and buyer alternate until someone
accepts, walks, or we hit the turn cap (terminal-only — the reward is computed
downstream in metrics.py from the agreed price and the secret floor)."""

from __future__ import annotations

from .buyer_sim import BuyerSimulator
from .models import BuyerPersona, Episode, Item, Outcome, Strategy
from .seller_agent import SellerAgent


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _finalize(item: Item, budget: float, *, deal: bool, price: float | None,
              turns: int, walked_by: str | None = None, reason: str = "") -> Outcome:
    surplus = skill = 0.0
    if deal and price is not None:
        surplus = _clip((price - item.floor_price) / max(item.list_price - item.floor_price, 1e-9))
        if budget > item.floor_price:
            skill = _clip((price - item.floor_price) / max(budget - item.floor_price, 1e-9))
    return Outcome(deal=deal, price=price, turns=turns, walked_by=walked_by,
                   reason=reason, surplus=surplus, skill=skill)


def run_episode(item: Item, persona: BuyerPersona, strategy: Strategy,
                max_turns: int = 6, store=None) -> Episode:
    seller = SellerAgent(item, strategy)
    buyer = BuyerSimulator(item, persona)
    ep = Episode(item=item, persona=persona, strategy_name=strategy.name)

    opening = seller.opening()
    ep.messages.append(opening)
    seller_ask = opening.offer or item.list_price

    outcome: Outcome | None = None
    for round_idx in range(1, max_turns + 1):
        bmsg = buyer.respond(ep, seller_ask, round_idx)
        ep.messages.append(bmsg)
        if bmsg.action == "accept":
            price = bmsg.offer if bmsg.offer is not None else seller_ask
            outcome = _finalize(item, buyer.budget, deal=True, price=price,
                                turns=round_idx, reason="buyer accepted")
            break
        if bmsg.action == "walk":
            outcome = _finalize(item, buyer.budget, deal=False, price=None,
                                turns=round_idx, walked_by="buyer", reason="buyer walked")
            break
        buyer_offer = bmsg.offer

        smsg = seller.respond(ep, buyer_offer, round_idx)
        ep.messages.append(smsg)
        if smsg.action == "accept":
            price = smsg.offer if smsg.offer is not None else buyer_offer
            outcome = _finalize(item, buyer.budget, deal=True, price=price,
                                turns=round_idx, reason="seller accepted")
            break
        if smsg.action == "walk":
            outcome = _finalize(item, buyer.budget, deal=False, price=None,
                                turns=round_idx, walked_by="seller", reason="seller walked")
            break
        if smsg.offer is not None:
            seller_ask = smsg.offer

    if outcome is None:
        outcome = _finalize(item, buyer.budget, deal=False, price=None,
                            turns=max_turns, reason="timeout")
    ep.outcome = outcome
    if store is not None:
        store.save_episode(ep, generation=strategy.gen)
    return ep
