"""Negotiation domain types — one validated Pydantic contract end-to-end.

Floor/budget invariants are encoded as validators (the integrity rails), not scattered
`if`s. `Knobs` is the *resolved* per-turn scalar set (the global parametric KnobPolicy,
a later slice, maps continuous features → Knobs; for now `Strategy` is the constant seed).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# --- canonical band helper (lower-inclusive edges; see docs/architecture.md conventions) ---

def band(x: float, edges: list[float]) -> str:
    """`x < edges[0] → low`, `edges[0] ≤ x < edges[1] → mid`, `x ≥ edges[1] → high`."""
    lo, hi = edges
    return "low" if x < lo else ("mid" if x < hi else "high")


class Item(BaseModel):
    """A thing being sold. `floor_price` is the seller's secret walk-away minimum."""

    name: str
    description: str = ""
    condition: str = "Used"
    list_price: float = Field(gt=0)      # public asking price
    target_price: float = Field(gt=0)    # the price we'd be happy with (guidance, not scored)
    floor_price: float = Field(gt=0)     # secret: never sell below this

    @model_validator(mode="after")
    def _floor_le_target_le_list(self):
        if not (self.floor_price <= self.target_price <= self.list_price):
            raise ValueError("require floor_price <= target_price <= list_price")
        return self

    @property
    def margin_ratio(self) -> float:
        return (self.list_price - self.floor_price) / self.list_price

    def public_blurb(self) -> str:
        return f"{self.name} ({self.condition}) — {self.description}. Listed at ${self.list_price:.0f}."


class BuyerPersona(BaseModel):
    """A simulated buyer. `budget_ratio` sets the hidden reservation as a fraction of
    list price; `family` tags the behavior policy so held-out can be a *different family*."""

    name: str
    style: str = ""
    budget_ratio: float = Field(gt=0)    # secret: max willingness = list_price * budget_ratio
    patience: int = Field(default=6, ge=1)
    eagerness: float = Field(default=0.5, ge=0.0, le=1.0)
    family: str = "heuristic"            # behavior-policy family (NOT just new params)


class Knobs(BaseModel):
    """The 5 resolved scalars used for one episode (bounds == the design's Field constraints)."""

    opening_anchor_ratio: float = Field(default=1.00, ge=0.90, le=1.00)
    concession_rate: float = Field(default=0.35, ge=0.05, le=0.80)
    accept_ratio: float = Field(default=0.92, ge=0.80, le=0.99)
    walkaway_patience: int = Field(default=7, ge=2, le=10)
    urgency: bool = False


class Strategy(Knobs):
    """The constant knob *seed* (a frozen-default `KnobPolicy`). Named for continuity with
    the design; carries no global tactics blob — lessons live per-bucket in the PolicyStore."""

    name: str = "baseline"


class Move(BaseModel):
    """One turn from either side. `reasoning` is private; `text` is what the opponent sees."""

    role: Literal["seller", "buyer"]
    text: str = ""
    action: Literal["talk", "offer", "accept", "walk"] = "talk"
    offer: float | None = None
    reasoning: str = ""                  # hidden scratchpad, excluded from transcript()

    @model_validator(mode="after")
    def _accept_needs_price(self):
        if self.action == "accept" and self.offer is None:
            raise ValueError("accept must name the agreed price")
        return self


class Outcome(BaseModel):
    deal: bool
    price: float | None = None
    turns: int = 0
    walked_by: Literal["seller", "buyer"] | None = None
    reason: str = ""
    surplus: float = Field(default=0.0, ge=0.0, le=1.0)  # (price-floor)/(list-floor) — vs floor
    skill: float = Field(default=0.0, ge=0.0, le=1.0)    # (price-floor)/(budget-floor) — vs hidden budget


class Episode(BaseModel):
    item: Item
    persona: BuyerPersona
    moves: list[Move] = Field(default_factory=list)
    outcome: Outcome | None = None

    def transcript(self) -> str:
        """Public transcript only — hidden reasoning is deliberately excluded."""
        out = []
        for m in self.moves:
            price = f" [${m.offer:.0f}]" if m.offer is not None else ""
            out.append(f"{m.role.upper()}{price}: {m.text}")
        return "\n".join(out)


def budget_of(item: Item, persona: BuyerPersona) -> int:
    """The buyer's hidden reservation price (ground truth, sim-only — the seller never sees it)."""
    return round(item.list_price * persona.budget_ratio)


def situation_key(item: Item, buyer_type: str = "unknown") -> str:
    """The coarse policy cell: `(margin_band, buyer_type)`. `price_band` is intentionally
    dropped — the reward is scale-invariant, so it would add bins, not signal. `buyer_type`
    stays `unknown` until belief inference exists (opponent.infer, a later slice)."""
    margin = band(item.margin_ratio, [0.15, 0.35])   # thin | mid | fat  (as low|mid|high)
    return f"{margin}/{buyer_type}"
