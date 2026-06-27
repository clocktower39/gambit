"""Scoring. The optimizer maximizes a VERIFIABLE surplus reward; the demo reports
the human-readable metric panel.

Per the negotiation-RL prior art (arXiv:2604.09855), the PRIMARY reward is a
deterministic, programmatic surplus from the secret floor — NOT an LLM judge.
That removes judge bias/variance and is itself the best anti-reward-hacking
defense (the judge would be the hackable component). An LLM judge can be added
later as a secondary qualitative tag, never the selector.
"""

from __future__ import annotations

from statistics import mean

from .models import BuyerPersona, Episode, Item, budget_of


def feasible(item: Item, persona: BuyerPersona) -> bool:
    """A deal is even possible only if the buyer's true max clears the floor."""
    return budget_of(item, persona) >= item.floor_price


def audit_episode(ep: Episode) -> tuple[bool, list[str]]:
    """Tier-1 reward-integrity guard (deterministic, no LLM): catch transcripts
    that only *look* like wins so the optimizer can't game its own reward.
    (Pattern borrowed from hud-trace-explorer's reward-hacking checks.)"""
    v: list[str] = []
    item, o = ep.item, ep.outcome
    floor = item.floor_price
    # The seller must never put a number at/under the secret floor on the table.
    for m in ep.messages:
        if m.role == "seller" and m.offer is not None and m.offer < floor - 1e-6:
            v.append(f"seller offered ${m.offer:.0f} below floor ${floor:.0f}")
    if o and o.deal:
        if o.price is None:
            v.append("deal recorded with no price")
        else:
            if o.price < floor - 1e-6:
                v.append(f"closed ${o.price:.0f} below floor ${floor:.0f}")
            offers = {round(m.offer) for m in ep.messages if m.offer is not None}
            if round(o.price) not in offers:
                v.append("agreed price never appeared in the transcript")
    return (not v, v)


def reward(ep: Episode) -> float:
    """Verifiable terminal reward in [-1, 1]:
      - integrity violation -> -1.0  (below floor / hallucinated close / leak)
      - no deal / walk-away ->  0.0  (neutral: don't punish walking from a bad buyer)
      - deal                -> surplus in [0, 1]  ((price - floor)/(list - floor))
    """
    ok, _ = audit_episode(ep)
    if not ok:
        return -1.0
    o = ep.outcome
    if o is None or not o.deal:
        return 0.0
    return o.surplus


# The optimizer and loop import score_episode; the verifiable reward IS the score.
score_episode = reward


def _first_offer_ratio(ep: Episode) -> float | None:
    opens = [m.offer for m in ep.messages if m.role == "seller" and m.offer is not None]
    return opens[0] / ep.item.list_price if opens else None


def summarize(episodes: list[Episode]) -> dict:
    if not episodes:
        return {}
    deals = [e for e in episodes if e.outcome and e.outcome.deal]
    feas = [e for e in episodes if feasible(e.item, e.persona)]
    feas_deals = [e for e in feas if e.outcome and e.outcome.deal]
    violations = [e for e in episodes if not audit_episode(e)[0]]
    first_offers = [r for r in (_first_offer_ratio(e) for e in episodes) if r is not None]
    return {
        "n": len(episodes),
        "score": mean(reward(e) for e in episodes),          # the verifiable selector
        "close_rate": (len(feas_deals) / len(feas)) if feas else 0.0,
        "avg_surplus": mean(e.outcome.surplus for e in deals) if deals else 0.0,
        "avg_skill": mean(e.outcome.skill for e in feas_deals) if feas_deals else 0.0,
        "avg_price": mean(e.outcome.price for e in deals) if deals else 0.0,
        "avg_turns": mean(e.outcome.turns for e in deals) if deals else 0.0,
        "first_offer_ratio": mean(first_offers) if first_offers else 0.0,  # anchor aggressiveness
        "overshoot_rate": len(violations) / len(episodes),                 # should trend to 0
        "deals": len(deals),
    }
