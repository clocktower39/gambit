"""The negotiator (seller). Its behavior is driven by a Strategy, which the
optimizer mutates over generations. Runs on the LLM when a key is present,
otherwise a deterministic heuristic so the loop is testable offline."""

from __future__ import annotations

from .config import llm_available
from .inference import chat_json
from .models import Episode, Item, Message, Strategy


class SellerAgent:
    def __init__(self, item: Item, strategy: Strategy):
        self.item = item
        self.strategy = strategy
        self.current_ask: float = round(item.list_price * strategy.opening_anchor_ratio)

    # --- public API ---------------------------------------------------------
    def opening(self) -> Message:
        text = (
            f"Hi! Thanks for your interest in the {self.item.name}. "
            f"I'm asking ${self.current_ask:.0f} — it's in {self.item.condition.lower()} condition."
        )
        return Message(role="seller", text=text, offer=self.current_ask, action="offer",
                       reasoning=f"open at anchor ${self.current_ask:.0f}; floor ${self.item.floor_price:.0f}")

    def respond(self, episode: Episode, buyer_offer: float | None, round_idx: int) -> Message:
        if llm_available():
            try:
                return self._llm_respond(episode, buyer_offer, round_idx)
            except Exception:
                pass  # fall back to heuristic on any API/parse failure
        return self._offline_respond(buyer_offer, round_idx)

    # --- heuristic ----------------------------------------------------------
    def _offline_respond(self, buyer_offer: float | None, round_idx: int) -> Message:
        s, item = self.strategy, self.item
        floor = item.floor_price
        acceptable = max(floor, item.list_price * s.accept_ratio)

        if buyer_offer is None:
            return self.opening()

        if buyer_offer >= self.current_ask:
            return Message("seller", "Deal — sold!", offer=self.current_ask, action="accept")
        if buyer_offer >= acceptable:
            return Message("seller", f"Okay, ${buyer_offer:.0f} works. Sold!",
                           offer=buyer_offer, action="accept")
        if buyer_offer < floor and round_idx >= s.walkaway_patience:
            return Message("seller", "That's well under what I can do — I'll pass. Thanks!",
                           action="walk")

        # Counter: concede a fraction of the gap toward the buyer, never below floor.
        target = max(buyer_offer, floor)
        new_ask = self.current_ask - s.concession_rate * (self.current_ask - target)
        new_ask = round(max(new_ask, floor))
        if new_ask <= buyer_offer:
            return Message("seller", f"Let's meet at ${buyer_offer:.0f}. Deal!",
                           offer=buyer_offer, action="accept")
        self.current_ask = new_ask
        nudge = " I do have a couple of other people asking, though." if s.urgency else ""
        return Message("seller", f"I can come down to ${new_ask:.0f}.{nudge}",
                       offer=new_ask, action="offer")

    # --- LLM ----------------------------------------------------------------
    def _llm_respond(self, episode: Episode, buyer_offer: float | None, round_idx: int) -> Message:
        s, item = self.strategy, self.item
        system = (
            "You are a sharp, friendly marketplace seller negotiating a sale. "
            "Maximize the final price while still closing the deal in a reasonable time. "
            f"SECRET FLOOR: never agree below ${item.floor_price:.0f}. "
            f"Target ${item.target_price:.0f}; you listed at ${item.list_price:.0f}. "
            f"Your current standing ask is ${self.current_ask:.0f}.\n"
            f"STRATEGY: {s.tactics}\n"
            f"Knobs — concession_rate={s.concession_rate}, accept above "
            f"${item.list_price * s.accept_ratio:.0f}, walk away from sub-floor buyers by "
            f"round {s.walkaway_patience}. Urgency tactics: {'on' if s.urgency else 'off'}.\n"
            'Reply ONLY as JSON: {"reasoning": "private notes (never shown to the buyer)", '
            '"text": "what you SAY to the buyer", "action": "offer|accept|walk", "offer": <number or null>}. '
            "Use action=accept with offer=<agreed price> to close; action=offer with offer=<your new ask> "
            "to counter; action=walk to end. Never go below the secret floor."
        )
        convo = episode.transcript() or "(no messages yet)"
        buyer_line = f"The buyer's latest offer is ${buyer_offer:.0f}." if buyer_offer else "Open the negotiation."
        user = f"Transcript so far:\n{convo}\n\n{buyer_line}\nRound {round_idx}. Respond as the seller."

        data = chat_json([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], temperature=0.6, max_tokens=220)

        action = str(data.get("action", "offer")).lower()
        offer = data.get("offer")
        offer = float(offer) if offer not in (None, "", "null") else None
        if action == "accept" and offer is not None:
            offer = max(offer, item.floor_price)
        if action == "offer" and offer is not None:
            self.current_ask = offer
        return Message("seller", str(data.get("text", "")).strip(), offer=offer, action=action,
                       reasoning=str(data.get("reasoning", "")).strip())
