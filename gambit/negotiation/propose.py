"""Negotiation proposer: candidate PolicyStores for the engine's improve loop.

KISS deterministic coordinate search over the GLOBAL parametric knobs (the offline learning
channel — text lessons are inert without an LLM, docs/strategy.md §8). Each candidate is one
atomic change (one knob ± a step, or the urgency toggle) so an accepted promotion is attributable.
"""

from __future__ import annotations

from .policy import PolicyStore
from gambit.engine import EpisodeResult

_KNOB_STEPS: dict[str, float] = {
    "concession_rate": 0.05,
    "accept_ratio": 0.02,
    "opening_anchor_ratio": 0.02,
    "walkaway_patience": 1,
}


def knob_nudges(store: PolicyStore, train_results: list[EpisodeResult] | None = None) -> list[PolicyStore]:
    base = store.knobs.base
    cands: list[PolicyStore] = []
    for field, step in _KNOB_STEPS.items():
        cur = getattr(base, field)
        for cand in (store.with_base(**{field: cur + step}), store.with_base(**{field: cur - step})):
            if cand.knobs.base != base:          # skip clamped no-ops (knob already at a bound)
                cands.append(cand)
    toggle = store.with_base(urgency=not base.urgency)
    if toggle.knobs.base != base:
        cands.append(toggle)
    return cands
