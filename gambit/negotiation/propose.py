"""Negotiation proposer: candidate PolicyStores for the engine's improve loop.

KISS deterministic coordinate search over the GLOBAL parametric knobs (the offline learning
channel — text lessons are inert without an LLM, docs/strategy.md §8). Each candidate is still one
*atomic* change (one knob moved, or the urgency toggle) so an accepted promotion is attributable —
but a knob is offered at a couple of step magnitudes (±1 and ±2 steps). The deterministic reward
landscape is rugged (dollar rounding creates flats and shallow dips), so a single fixed step gets
trapped on the first plateau; the extra magnitude lets the greedy search step over a trivial dip
to the real local optimum without sacrificing attributability or determinism.
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


def knob_nudges(store: PolicyStore, train_results: list[EpisodeResult] | None = None) -> list[PolicyStore]:
    base = store.knobs.base
    cands: list[PolicyStore] = []
    seen: set[tuple] = set()                  # dedup clamp-collapsed candidates (the gate is the costly part)
    for field, step in _KNOB_STEPS.items():
        cur = getattr(base, field)
        for m in _STEP_MULTS:
            for cand in (store.with_base(**{field: cur + m * step}), store.with_base(**{field: cur - m * step})):
                cb = cand.knobs.base
                if cb == base:                # skip clamped no-ops (knob already at a bound)
                    continue
                key = tuple(sorted(cb.model_dump().items()))
                if key not in seen:
                    seen.add(key)
                    cands.append(cand)
    toggle = store.with_base(urgency=not base.urgency)
    if toggle.knobs.base != base:
        cands.append(toggle)
    return cands
