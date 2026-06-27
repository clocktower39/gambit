"""Adversarial buyer simulator. Each buyer has a hidden reservation price
(`budget`, derived from the persona's budget_ratio and the item's list price) and
a persona. The negotiator never sees the budget; it's used only for scoring.

A reservation guard enforces the paper's key anti-gaming rule: the simulated buyer
can NEVER accept above its hidden budget, no matter how the seller talks — so the
optimizer can't learn to "talk up" a gullible simulator instead of negotiating.
"""

from __future__ import annotations

from .config import llm_available, settings
from .inference import chat_json
from .models import BuyerPersona, Episode, Item, Message, budget_of


class BuyerSimulator:
    def __init__(self, item: Item, persona: BuyerPersona):
        self.item = item
        self.persona = persona
        self.budget = budget_of(item, persona)  # hidden reservation price
        self.current_offer: float | None = None

    def respond(self, episode: Episode, seller_ask: float, round_idx: int) -> Message:
        if llm_available():
            try:
                msg = self._llm_respond(episode, seller_ask, round_idx)
            except Exception:
                msg = self._offline_respond(seller_ask, round_idx)
        else:
            msg = self._offline_respond(seller_ask, round_idx)
        return self._enforce_reservation(msg, seller_ask)

    # Reservation guard — applied to every buyer move regardless of mode.
    def _enforce_reservation(self, msg: Message, seller_ask: float) -> Message:
        if msg.action == "accept" and seller_ask > self.budget + 1e-6:
            # Physically cannot accept above budget — counter at the limit instead.
            self.current_offer = float(self.budget)
            return Message("buyer", f"That's over my limit — ${self.budget:.0f} is the most I can do.",
                           offer=float(self.budget), action="offer",
                           reasoning=msg.reasoning or "reservation guard: cannot exceed budget")
        if msg.offer is not None and msg.offer > self.budget + 1e-6:
            msg.offer = float(self.budget)
            self.current_offer = float(self.budget)
        return msg

    # --- heuristic ----------------------------------------------------------
    def _offline_respond(self, seller_ask: float, round_idx: int) -> Message:
        p, budget = self.persona, self.budget

        if self.current_offer is None:  # opening lowball, anchored below budget
            opening = round(min(seller_ask - 1, budget * (0.55 + 0.15 * p.eagerness)))
            self.current_offer = max(opening, 1)
            return Message("buyer", f"Would you take ${self.current_offer:.0f}?",
                           offer=self.current_offer, action="offer",
                           reasoning=f"budget {budget}; open low")

        if round_idx >= p.patience:
            return Message("buyer", "Thanks, but it's more than I want to spend. I'll keep looking.",
                           action="walk", reasoning="out of patience")

        if seller_ask <= budget:
            comfort = budget * (0.85 + 0.10 * p.eagerness)
            if seller_ask <= comfort or seller_ask <= self.current_offer:
                return Message("buyer", f"Deal — ${seller_ask:.0f} it is.",
                               offer=seller_ask, action="accept",
                               reasoning=f"within budget {budget}, comfortable")
            ceiling = min(seller_ask, budget)
            self.current_offer = round(min(self.current_offer + (ceiling - self.current_offer) * (0.30 + 0.30 * p.eagerness), ceiling))
            return Message("buyer", f"I could go ${self.current_offer:.0f}.",
                           offer=self.current_offer, action="offer",
                           reasoning=f"ask {seller_ask} <= budget {budget}; nudge up")

        # Ask is above budget: creep toward (never past) budget, then stall.
        self.current_offer = round(min(self.current_offer + (budget - self.current_offer) * (0.25 + 0.25 * p.eagerness), budget))
        return Message("buyer", f"That's a bit high. ${self.current_offer:.0f} is about my limit.",
                       offer=self.current_offer, action="offer",
                       reasoning=f"ask {seller_ask} > budget {budget}; hold near limit")

    # --- LLM ----------------------------------------------------------------
    def _llm_respond(self, episode: Episode, seller_ask: float, round_idx: int) -> Message:
        p, item = self.persona, self.item
        system = (
            f"You are a marketplace BUYER negotiating for: {item.public_blurb()}\n"
            f"PERSONA: {p.style}\n"
            f"SECRET MAX you will pay: ${self.budget:.0f}. NEVER reveal this number and NEVER pay above it. "
            f"You have ~{p.patience} rounds of patience; eagerness {p.eagerness:.1f}/1. "
            "Open low, haggle realistically in character, and close if the price is good for you.\n"
            'Reply ONLY as JSON: {"reasoning": "private notes (never shown to the seller)", '
            '"text": "what you SAY to the seller", "action": "offer|accept|walk", "offer": <number or null>}. '
            "action=accept with offer=<price> to buy; action=offer with offer=<your counter>; action=walk to leave."
        )
        user = (
            f"Transcript so far:\n{episode.transcript() or '(no messages yet)'}\n\n"
            f"The seller's standing ask is ${seller_ask:.0f}. Round {round_idx}. Respond as the buyer."
        )
        data = chat_json([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], model=settings.buyer_model, temperature=0.8, max_tokens=240)

        action = str(data.get("action", "offer")).lower()
        offer = data.get("offer")
        offer = float(offer) if offer not in (None, "", "null") else None
        if offer is not None:
            self.current_offer = offer
        return Message("buyer", str(data.get("text", "")).strip(), offer=offer, action=action,
                       reasoning=str(data.get("reasoning", "")).strip())
