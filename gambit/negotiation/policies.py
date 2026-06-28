"""Deterministic seller policy + buyer counterparty (no LLM).

These are the offline, reproducible implementations behind the seam: the seller is driven
by `Knobs`; the buyer is a behavior *family* with a hard reservation guard. Methods are
stateless given the dynamic args (the referee tracks `current_ask`/`current_offer`), so a
run is fully determined by inputs — the basis for paired-seed A/B later.
"""

from __future__ import annotations

from .models import BuyerPersona, Item, Knobs, Move, budget_of


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

    def __init__(self, knobs: Knobs, name: str = "seed"):
        self.knobs = knobs
        self.name = name

    def opening_ask(self, item: Item) -> float:
        return round(item.list_price * self.knobs.opening_anchor_ratio)

    def opening(self, item: Item) -> Move:
        ask = self.opening_ask(item)
        return Move(role="seller", action="offer", offer=ask,
                    text=f"Thanks for your interest in the {item.name}. I'm asking ${ask:.0f}.",
                    reasoning=f"open at anchor ${ask:.0f}; floor ${item.floor_price:.0f}")

    def respond(self, item: Item, current_ask: float, buyer_offer: float | None, round_idx: int) -> Move:
        """Return the seller's move. `offer` on an `offer` action is the new standing ask."""
        k, floor = self.knobs, item.floor_price
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
