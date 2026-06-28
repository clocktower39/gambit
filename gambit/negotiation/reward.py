"""Deterministic, verifiable reward + Tier-1 integrity audit. NO LLM in the selector.

Per the negotiation-RL prior art (arXiv:2604.09855), the primary reward is a programmatic
surplus from the secret floor — that removes judge bias/variance and is itself the best
anti-reward-hacking defense (the judge would be the hackable component). The Tier-1 audit
catches transcripts that only *look* like wins, so the optimizer can't game its own metric.
"""

from __future__ import annotations

from .models import Episode


def audit_episode(ep: Episode) -> list[str]:
    """Tier-1 reward-integrity guard (deterministic). Returns the list of violations
    (empty == clean). Catches below-floor offers/closes and hallucinated prices."""
    v: list[str] = []
    item, o = ep.item, ep.outcome
    floor = item.floor_price
    for m in ep.moves:
        if m.role == "seller" and m.offer is not None and m.offer < floor - 1e-6:
            v.append(f"seller offered ${m.offer:.0f} below floor ${floor:.0f}")
    if o and o.deal:
        if o.price is None:
            v.append("deal recorded with no price")
        else:
            if o.price < floor - 1e-6:
                v.append(f"closed ${o.price:.0f} below floor ${floor:.0f}")
            offers = {round(m.offer) for m in ep.moves if m.offer is not None}
            if round(o.price) not in offers:
                v.append("agreed price never appeared in the transcript")
    return v


def reward(ep: Episode) -> float:
    """Verifiable terminal reward in [-1, 1]:
      integrity violation -> -1.0 · no-deal / walk-away -> 0.0 · deal -> surplus in [0, 1].
    Walking from a bad buyer is neutral, not punished."""
    if audit_episode(ep):
        return -1.0
    o = ep.outcome
    if o is None or not o.deal:
        return 0.0
    return o.surplus
