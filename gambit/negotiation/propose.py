"""Negotiation proposer: candidate PolicyStores for the engine's improve loop.

KISS deterministic coordinate search over the GLOBAL parametric policy (the offline learning
channel — text lessons are inert without an LLM, docs/strategy.md §8). Each candidate is still one
*atomic* change: one base knob moved, one feature coefficient moved, or the urgency toggle. A knob
is offered at a couple of step magnitudes (±1 and ±2 steps). The deterministic reward landscape is
rugged (dollar rounding creates flats and shallow dips), so the extra magnitude lets the greedy
search step over a trivial dip without sacrificing attributability or determinism.
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
_STEP_MULTS: tuple[int, ...] = (1, 2)   # a knob is nudged by ±1 and ±2 steps (escapes rugged-landscape plateaus)

_COEFF_STEPS: dict[tuple[str, str], float] = {
    ("concession_rate", "thin_margin"): 0.05,
    ("concession_rate", "fat_margin"): 0.05,
    ("concession_rate", "reservation_gap"): 0.04,
    ("concession_rate", "turn_frac"): 0.04,
    ("concession_rate", "urgency"): 0.04,
    ("concession_rate", "active_buyers"): 0.04,
    ("concession_rate", "best_offer_gap"): 0.04,
    ("concession_rate", "listing_age"): 0.04,
    ("concession_rate", "inventory_pressure"): 0.04,
    ("concession_rate", "bundle_opportunity"): 0.04,
    ("accept_ratio", "thin_margin"): 0.02,
    ("accept_ratio", "fat_margin"): 0.02,
    ("accept_ratio", "turn_frac"): 0.01,
    ("accept_ratio", "urgency"): 0.01,
    ("accept_ratio", "active_buyers"): 0.01,
    ("accept_ratio", "listing_age"): 0.01,
    ("accept_ratio", "inventory_pressure"): 0.01,
    ("accept_ratio", "bundle_opportunity"): 0.01,
    ("walkaway_patience", "thin_margin"): 0.50,
    ("walkaway_patience", "reservation_gap"): 0.50,
    ("walkaway_patience", "urgency"): 0.50,
    ("walkaway_patience", "active_buyers"): 0.50,
    ("walkaway_patience", "listing_age"): 0.50,
    ("walkaway_patience", "inventory_pressure"): 0.50,
}


def knob_nudges(store: PolicyStore, train_results: list[EpisodeResult] | None = None) -> list[PolicyStore]:
    base = store.knobs.base
    cands: list[PolicyStore] = []
    seen: set[tuple] = set()                  # dedup clamp-collapsed candidates (the gate is the costly part)

    def add(cand: PolicyStore) -> None:
        key = cand.knobs.model_dump_json()
        if key not in seen:
            seen.add(key)
            cands.append(cand)

    for field, step in _KNOB_STEPS.items():
        cur = getattr(base, field)
        for m in _STEP_MULTS:
            for cand in (store.with_base(**{field: cur + m * step}), store.with_base(**{field: cur - m * step})):
                cb = cand.knobs.base
                if cb == base:                # skip clamped no-ops (knob already at a bound)
                    continue
                add(cand)
    if store.knobs.shaped:
        for (knob, feature), step in _COEFF_STEPS.items():
            for m in _STEP_MULTS:
                add(store.with_coeff(knob, feature, m * step))
                add(store.with_coeff(knob, feature, -m * step))
    toggle = store.with_base(urgency=not base.urgency)
    if toggle.knobs.base != base:
        add(toggle)
    return cands
