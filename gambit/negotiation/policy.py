"""The learned artifact for negotiation — the hybrid PolicyStore.

Two channels (docs/architecture.md "the learned artifact", docs/strategy.md §5/§6):
  - a GLOBAL parametric KnobPolicy: the 5 scalars resolved from continuous, scale-free
    Features, with globally-shared params (pooled sample strength). The optimizer tunes
    both the `base` knobs and feature coefficients; doctrine is seed data, not fixed code.
  - a per-bucket text-lesson table keyed by situation_key. INERT in the offline engine
    (no LLM reads text) — exercised once the typed LLM seller lands (slice 5). Kept here so
    the structure is real and seedable from the strategy prior.

Offline, learning lives in the parametric knobs + coefficients (docs/strategy.md §8: the engine
exercises the knob spine). KISS: no Beta/Thompson/demotion yet — added only if a measured effect needs it.
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

_FEATURES: tuple[str, ...] = ("thin_margin", "fat_margin", "reservation_gap", "turn_frac", "urgency")


def _default_coeffs() -> dict[str, dict[str, float]]:
    """Cold-start strategy prior as policy data. The optimizer can mutate these weights."""
    return {
        "concession_rate": {
            "thin_margin": -0.50,
            "fat_margin": 0.30,
            "reservation_gap": 0.08,
            "turn_frac": -0.10,
            "urgency": 0.15,
        },
        "accept_ratio": {
            "thin_margin": 0.20,
            "fat_margin": -0.12,
            "turn_frac": -0.04,
            "urgency": -0.08,
        },
        "walkaway_patience": {
            "thin_margin": -2.0,
            "reservation_gap": -1.0,
            "urgency": -2.0,
        },
    }


def _clamp(field: str, val: float) -> float:
    lo, hi = _BOUNDS[field]
    return max(lo, min(hi, val))


class Features(BaseModel):
    """Continuous, scale-free decision features (the KnobPolicy's input)."""

    margin_ratio: float              # (list - floor) / list
    reservation_gap: float = 0.0      # (standing ask - observed buyer offer) / list; proxy until opponent.infer
    turn_frac: float = 0.0            # round_idx / max_turns
    urgency: float = 0.0              # seller time pressure, 0..1

    def values(self) -> dict[str, float]:
        """Feature basis used by the global coefficient policy."""
        return {
            "thin_margin": max(0.0, 0.30 - self.margin_ratio),
            "fat_margin": max(0.0, self.margin_ratio - 0.30),
            "reservation_gap": _clamp_value(self.reservation_gap, -1.0, 1.0),
            "turn_frac": _clamp_value(self.turn_frac, 0.0, 1.0),
            "urgency": _clamp_value(self.urgency, 0.0, 1.0),
        }


class KnobPolicy(BaseModel):
    """Global parametric knob policy. `base` + `coeffs` are what the optimizer tunes.

    `shaped` toggles the situation-keying for the substrate ablation (eval-plan §N3): when True
    (the hybrid PolicyStore substrate) `resolve` conditions the knobs on feature coefficients; when
    False (the 'uniform global' ablation) it applies one flat knob set to every situation. Both
    share the same optimizer + gate — the ablation isolates the *substrate*, not the search."""

    base: Knobs = Field(default_factory=Knobs)
    coeffs: dict[str, dict[str, float]] = Field(default_factory=_default_coeffs)
    shaped: bool = True

    def resolve(self, f: Features) -> Knobs:
        """base + learned feature coefficients → the per-turn Knobs (clamped to valid ranges).

        With `shaped=False` the feature coefficients are ignored — the uniform-global ablation substrate."""
        b = self.base
        values = f.values() if self.shaped else {}

        def resolved(field: str, default: float) -> float:
            weights = self.coeffs.get(field, {})
            return default + sum(weights.get(name, 0.0) * value for name, value in values.items())

        return Knobs(
            opening_anchor_ratio=_clamp("opening_anchor_ratio", resolved("opening_anchor_ratio", b.opening_anchor_ratio)),
            concession_rate=_clamp("concession_rate", resolved("concession_rate", b.concession_rate)),
            accept_ratio=_clamp("accept_ratio", resolved("accept_ratio", b.accept_ratio)),
            walkaway_patience=int(round(_clamp("walkaway_patience", resolved("walkaway_patience", b.walkaway_patience)))),
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

    def with_base(self, **changes: object) -> "PolicyStore":
        """Return a copy with `base` knobs nudged + clamped — the unit of knob proposals."""
        data = self.knobs.base.model_dump()
        for field, val in changes.items():
            if field in _BOUNDS:
                val = _clamp(field, float(val))
                if field == "walkaway_patience":
                    val = int(round(val))
            data[field] = val
        new_knobs = self.knobs.model_copy(update={"base": Knobs(**data)})
        return self.model_copy(update={"knobs": new_knobs})

    def with_coeff(self, knob: str, feature: str, delta: float) -> "PolicyStore":
        """Return a copy with one coefficient nudged — the learned parametric channel."""
        if knob not in _BOUNDS or feature not in _FEATURES:
            raise ValueError(f"unknown coefficient {knob}.{feature}")
        coeffs = {k: dict(v) for k, v in self.knobs.coeffs.items()}
        weights = coeffs.setdefault(knob, {})
        weights[feature] = weights.get(feature, 0.0) + delta
        new_knobs = self.knobs.model_copy(update={"coeffs": coeffs})
        return self.model_copy(update={"knobs": new_knobs})

    def promoted_lessons(self, bucket: str) -> list[str]:
        bp = self.buckets.get(bucket)
        return [l.text for l in bp.lessons if l.promoted] if bp else []


def _clamp_value(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
