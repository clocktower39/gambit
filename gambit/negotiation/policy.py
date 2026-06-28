"""The learned artifact for negotiation — the hybrid PolicyStore.

Two channels (docs/architecture.md "the learned artifact", docs/strategy.md §5/§6):
  - a GLOBAL parametric KnobPolicy: the 5 scalars resolved from continuous, scale-free
    Features, with globally-shared params (pooled sample strength). The optimizer tunes
    the `base` knobs; `resolve` applies fixed doctrine shaping (thin margin → protect the wall).
  - a per-bucket text-lesson table keyed by situation_key. INERT in the offline engine
    (no LLM reads text) — exercised once the typed LLM seller lands (slice 5). Kept here so
    the structure is real and seedable from the strategy prior.

Offline, learning lives in the parametric knobs (docs/strategy.md §8: the engine exercises
the knob spine). KISS: no Beta/Thompson/demotion yet — added only if a measured effect needs it.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .models import Knobs

# Bounds mirror the Knobs Field constraints; used to clamp proposed/​resolved knobs.
_BOUNDS: dict[str, tuple[float, float]] = {
    "opening_anchor_ratio": (0.90, 1.00),
    "concession_rate": (0.05, 0.80),
    "accept_ratio": (0.80, 0.99),
    "walkaway_patience": (2, 10),
}


def _clamp(field: str, val: float) -> float:
    lo, hi = _BOUNDS[field]
    return max(lo, min(hi, val))


class Features(BaseModel):
    """Continuous, scale-free decision features (the KnobPolicy's input)."""

    margin_ratio: float          # (list - floor) / list
    urgency: float = 0.0         # seller time pressure, 0..1
    # reservation_gap / turns_elapsed land with opponent.infer + per-turn resolution (later slice)


class KnobPolicy(BaseModel):
    """Global parametric knob policy. `base` is what the optimizer tunes (shared across buckets)."""

    base: Knobs = Field(default_factory=Knobs)

    def resolve(self, f: Features) -> Knobs:
        """base + fixed doctrine shaping → the per-episode Knobs (clamped to valid ranges).
        Doctrine (strategy.md §5): thinner margin ⇒ protect the wall (concede less, accept higher)."""
        b = self.base
        adj = 0.30 - f.margin_ratio          # >0 when thin, <0 when fat
        return Knobs(
            opening_anchor_ratio=_clamp("opening_anchor_ratio", b.opening_anchor_ratio),
            concession_rate=_clamp("concession_rate", b.concession_rate - 0.5 * adj),
            accept_ratio=_clamp("accept_ratio", b.accept_ratio + 0.2 * adj),
            walkaway_patience=int(_clamp("walkaway_patience", b.walkaway_patience)),
            urgency=b.urgency,
        )


class Lesson(BaseModel):
    """A per-bucket text lesson. Promotion stats kept minimal (KISS) — paired-A/B delta + support."""

    text: str
    promoted: bool = False
    gate_delta: float = 0.0      # held-out reward Δ (with − without) at promotion
    support: int = 0             # paired held-out seeds behind gate_delta


class BucketPolicy(BaseModel):
    lessons: list[Lesson] = Field(default_factory=list)


class PolicyStore(BaseModel):
    """THE learned artifact: a global parametric knob policy + per-bucket lessons."""

    knobs: KnobPolicy = Field(default_factory=KnobPolicy)
    buckets: dict[str, BucketPolicy] = Field(default_factory=dict)

    def with_base(self, **changes: float) -> "PolicyStore":
        """Return a copy with `base` knobs nudged + clamped — the unit of knob proposals."""
        data = self.knobs.base.model_dump()
        for field, val in changes.items():
            if field in _BOUNDS:
                val = _clamp(field, val)
                if field == "walkaway_patience":
                    val = int(round(val))
            data[field] = val
        new_knobs = self.knobs.model_copy(update={"base": Knobs(**data)})
        return self.model_copy(update={"knobs": new_knobs})

    def promoted_lessons(self, bucket: str) -> list[str]:
        bp = self.buckets.get(bucket)
        return [l.text for l in bp.lessons if l.promoted] if bp else []
