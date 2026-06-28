"""Deterministic seller policy + buyer counterparty (no LLM).

These are the offline, reproducible implementations behind the seam: the seller is driven
by `Knobs`; the buyer is a behavior *family* with a hard reservation guard. Methods are
stateless given the dynamic args (the referee tracks `current_ask`/`current_offer`), so a
run is fully determined by inputs — the basis for paired-seed A/B later.
"""

from __future__ import annotations

from typing import Protocol

from .models import BuyerPersona, Item, Knobs, Move, budget_of
from .policy import Features, KnobPolicy


class SellerPolicy(Protocol):
    """What the referee needs from a seller — satisfies the engine's opaque `Policy`.
    Slice 2's parametric / LLM sellers implement this same shape."""

    def opening(self, item: Item) -> Move: ...
    def respond(self, item: Item, current_ask: float, buyer_offer: float | None, round_idx: int) -> Move: ...


class BuyerCounterparty(Protocol):
    """What the referee needs from a buyer — satisfies the engine's `Counterparty`.
    `family` lets held-out be a *different behavior family*, not the same sim re-parameterized."""

    family: str
    persona: BuyerPersona

    def respond(self, item: Item, seller_ask: float, round_idx: int, current_offer: float | None) -> Move: ...


def enforce_reservation(move: Move, budget: float) -> Move:
    """Hard rail applied to EVERY buyer move regardless of family: a buyer can never accept
    above its hidden budget, nor offer above it — so a seller can't 'talk up' a gullible sim."""
    if move.action == "accept" and move.offer is not None and move.offer > budget + 1e-6:
        return Move(role="buyer", action="offer", offer=float(budget),
                    text=f"That's over my limit — ${budget:.0f} is the most I can do.",
                    reasoning="reservation guard: cannot exceed budget")
    if move.offer is not None and move.offer > budget + 1e-6:
        return move.model_copy(update={"offer": float(budget)})
    return move


class KnobSellerPolicy:
    """The seller. Behavior is fully determined by `Knobs` (the per-bucket lessons channel
    arrives in a later slice). Implements the engine's opaque `Policy`."""

    def __init__(self, knobs: Knobs | KnobPolicy, name: str = "seed", max_turns: int = 6):
        self.knob_policy = knobs if isinstance(knobs, KnobPolicy) else KnobPolicy(base=knobs, coeffs={})
        self.name = name
        self.max_turns = max_turns

    def _knobs(
        self,
        item: Item,
        *,
        current_ask: float | None = None,
        buyer_offer: float | None = None,
        round_idx: int = 0,
    ) -> Knobs:
        ask = current_ask if current_ask is not None else item.list_price
        gap = 0.0 if buyer_offer is None else (ask - buyer_offer) / item.list_price
        return self.knob_policy.resolve(Features(
            margin_ratio=item.margin_ratio,
            reservation_gap=gap,
            turn_frac=round_idx / max(self.max_turns, 1),
            urgency=1.0 if self.knob_policy.base.urgency else 0.0,
        ))

    def opening_ask(self, item: Item) -> float:
        return round(item.list_price * self._knobs(item).opening_anchor_ratio)

    def opening(self, item: Item) -> Move:
        ask = self.opening_ask(item)
        return Move(role="seller", action="offer", offer=ask,
                    text=f"Thanks for your interest in the {item.name}. I'm asking ${ask:.0f}.",
                    reasoning=f"open at anchor ${ask:.0f}; floor ${item.floor_price:.0f}")

    def respond(self, item: Item, current_ask: float, buyer_offer: float | None, round_idx: int) -> Move:
        """Return the seller's move. `offer` on an `offer` action is the new standing ask."""
        k, floor = self._knobs(item, current_ask=current_ask, buyer_offer=buyer_offer, round_idx=round_idx), item.floor_price
        if buyer_offer is None:
            return self.opening(item)
        acceptable = max(floor, item.list_price * k.accept_ratio)
        if buyer_offer >= current_ask:
            return Move(role="seller", action="accept", offer=current_ask, text="Deal — sold!")
        if buyer_offer >= acceptable:
            return Move(role="seller", action="accept", offer=buyer_offer,
                        text=f"Okay, ${buyer_offer:.0f} works. Sold!")
        if buyer_offer < floor and round_idx >= k.walkaway_patience:
            return Move(role="seller", action="walk",
                        text="That's well under what I can do — I'll pass. Thanks!")
        target = max(buyer_offer, floor)
        new_ask = round(max(current_ask - k.concession_rate * (current_ask - target), floor))
        if new_ask <= buyer_offer:
            return Move(role="seller", action="accept", offer=buyer_offer,
                        text=f"Let's meet at ${buyer_offer:.0f}. Deal!")
        nudge = " I do have a couple of other people asking, though." if k.urgency else ""
        return Move(role="seller", action="offer", offer=new_ask,
                    text=f"I can come down to ${new_ask:.0f}.{nudge}")


class HeuristicBuyer:
    """A reservation-respecting buyer behavior family. Implements the engine's `Counterparty`."""

    family = "heuristic"

    def __init__(self, persona: BuyerPersona):
        self.persona = persona

    def budget(self, item: Item) -> int:
        return budget_of(item, self.persona)

    def respond(self, item: Item, seller_ask: float, round_idx: int, current_offer: float | None) -> Move:
        p, budget = self.persona, self.budget(item)
        if current_offer is None:  # opening lowball, anchored below budget
            opening = max(round(min(seller_ask - 1, budget * (0.55 + 0.15 * p.eagerness))), 1)
            move = Move(role="buyer", action="offer", offer=float(opening),
                        text=f"Would you take ${opening:.0f}?", reasoning="open low")
        elif round_idx >= p.patience:
            move = Move(role="buyer", action="walk",
                        text="Thanks, but it's more than I want to spend. I'll keep looking.",
                        reasoning="out of patience")
        elif seller_ask <= budget:
            comfort = budget * (0.85 + 0.10 * p.eagerness)
            if seller_ask <= comfort or seller_ask <= current_offer:
                move = Move(role="buyer", action="accept", offer=float(seller_ask),
                            text=f"Deal — ${seller_ask:.0f} it is.", reasoning="within budget, comfortable")
            else:
                ceiling = min(seller_ask, budget)
                nxt = round(min(current_offer + (ceiling - current_offer) * (0.30 + 0.30 * p.eagerness), ceiling))
                move = Move(role="buyer", action="offer", offer=float(nxt),
                            text=f"I could go ${nxt:.0f}.", reasoning="nudge up under budget")
        else:  # ask above budget: creep toward (never past) budget
            nxt = round(min(current_offer + (budget - current_offer) * (0.25 + 0.25 * p.eagerness), budget))
            move = Move(role="buyer", action="offer", offer=float(nxt),
                        text=f"That's a bit high. ${nxt:.0f} is about my limit.", reasoning="hold near limit")
        return enforce_reservation(move, budget)


class FirmAnchorBuyer:
    """A *structurally different* buyer family — the honest held-out (build-order #3, eval-plan §2).

    HeuristicBuyer creeps monotonically UP toward its budget and accepts once a deal feels
    "comfortable"; a seller can exploit that by simply holding firm. FirmAnchorBuyer plays a
    different decision rule entirely: it plants one principled anchor *below* budget and HOLDS it,
    conceding essentially nothing, accepting only when the seller meets the anchor — with a single
    rational endgame accept (up to its true budget) right before it runs out of patience, else it
    walks. This is a different behavior *policy*, not HeuristicBuyer re-parameterized, so a seller
    tuned against eager creep does not automatically transfer here. That is exactly what makes it a
    valid held-out: improvement on it is improvement that generalizes. Stateless and deterministic
    (its standing offer is a pure function of the args), so paired-seed A/B stays reproducible."""

    family = "firm_anchor"

    def __init__(self, persona: BuyerPersona):
        self.persona = persona

    def budget(self, item: Item) -> int:
        return budget_of(item, self.persona)

    def _anchor(self, budget: int) -> float:
        # Principled anchor strictly below budget: firmer (higher) when eager, lower for lowballers.
        return float(round(min(budget - 1, budget * (0.72 + 0.12 * self.persona.eagerness))))

    def respond(self, item: Item, seller_ask: float, round_idx: int, current_offer: float | None) -> Move:
        p, budget = self.persona, self.budget(item)
        anchor = self._anchor(budget)
        if current_offer is None:                       # open AT the anchor (a stated fair price, not a throwaway lowball)
            move = Move(role="buyer", action="offer", offer=anchor,
                        text=f"I can do ${anchor:.0f} — that's a fair price for me.", reasoning="plant firm anchor")
        elif seller_ask <= anchor:                      # seller met the anchor → take it
            move = Move(role="buyer", action="accept", offer=float(seller_ask),
                        text=f"${seller_ask:.0f} works — deal.", reasoning="seller met anchor")
        elif round_idx >= p.patience:                   # endgame: one rational accept up to true budget, else walk
            if seller_ask <= budget:
                move = Move(role="buyer", action="accept", offer=float(seller_ask),
                            text=f"Alright, ${seller_ask:.0f} — I'll take it.", reasoning="endgame rational accept")
            else:
                move = Move(role="buyer", action="walk",
                            text="We're too far apart. I'll pass.", reasoning="held firm; seller stayed above budget")
        else:                                           # hold the line — re-assert the anchor (barely moves)
            hold = float(round(min(budget, max(current_offer, anchor))))
            move = Move(role="buyer", action="offer", offer=hold,
                        text=f"I'm firm around ${hold:.0f}.", reasoning="hold anchor")
        return enforce_reservation(move, budget)
