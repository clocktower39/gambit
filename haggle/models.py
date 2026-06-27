"""Core domain types for negotiation episodes."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Item:
    """A thing being sold. floor_price is the seller's secret walk-away minimum."""

    name: str
    description: str
    condition: str
    list_price: float       # public asking price
    target_price: float     # the price we'd be happy with
    floor_price: float       # secret: never sell below this

    def public_blurb(self) -> str:
        return f"{self.name} ({self.condition}) — {self.description}. Listed at ${self.list_price:.0f}."


@dataclass
class BuyerPersona:
    """A simulated buyer. `budget_ratio` sets the hidden reservation price as a
    fraction of the item's list price, so personas behave consistently across items."""

    name: str
    style: str               # how they negotiate, in natural language
    budget_ratio: float      # secret: max willingness = list_price * budget_ratio
    patience: int = 6        # turns before they walk
    eagerness: float = 0.5   # 0 = only buys at a steal, 1 = wants it badly


@dataclass
class Message:
    role: str                       # "seller" | "buyer"
    text: str                       # the public <dialogue> — what the opponent sees
    offer: Optional[float] = None   # a concrete price on the table, if any
    action: str = "talk"            # "talk" | "offer" | "accept" | "walk"
    reasoning: str = ""             # hidden <reasoning> scratchpad — never shown to the opponent


@dataclass
class Strategy:
    """The negotiator's policy — the thing the optimizer mutates over generations."""

    name: str = "baseline"
    gen: int = 0
    opening_anchor_ratio: float = 1.0   # open at list_price * this
    concession_rate: float = 0.35       # fraction of the gap conceded per round
    accept_ratio: float = 0.92          # accept buyer offers >= list_price * this
    walkaway_patience: int = 7          # turns before abandoning a too-low buyer
    urgency: bool = False               # deploy scarcity / "other buyers" tactics
    tactics: str = (
        "Be warm but firm. Anchor near the list price, justify the value, and "
        "concede slowly. Protect the floor and aim for the target."
    )

    def clone(self, **changes) -> "Strategy":
        data = asdict(self)
        data.update(changes)
        return Strategy(**data)


@dataclass
class Outcome:
    deal: bool
    price: Optional[float]
    turns: int
    walked_by: Optional[str] = None  # "seller" | "buyer" | None
    reason: str = ""
    surplus: float = 0.0             # (price - floor) / (list - floor), clipped to [0,1]
    skill: float = 0.0               # (price - floor) / (budget - floor) — how much of the
                                     # buyer's true willingness we extracted; 0..1


@dataclass
class Episode:
    item: Item
    persona: BuyerPersona
    strategy_name: str
    messages: list[Message] = field(default_factory=list)
    outcome: Optional[Outcome] = None

    def transcript(self) -> str:
        """Public transcript only — hidden reasoning is deliberately excluded."""
        lines = []
        for m in self.messages:
            tag = m.role.upper()
            price = f" [${m.offer:.0f}]" if m.offer is not None else ""
            lines.append(f"{tag}{price}: {m.text}")
        return "\n".join(lines)


def budget_of(item: Item, persona: BuyerPersona) -> int:
    """The buyer's hidden reservation price for this item (ground truth, sim-only)."""
    return round(item.list_price * persona.budget_ratio)
