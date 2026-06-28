"""Portfolio/marketplace state for one seller negotiating many buyer threads.

The current `NegotiationDomain` is intentionally one listing x one buyer. This module is the
non-invasive seam for the next domain: one seller policy managing multiple listings and parallel
buyers, while each buyer still only sees its own thread.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .models import Item
from .policy import Features


class ListingState(BaseModel):
    """Seller-visible state for one listing in the portfolio."""

    listing_id: str
    item: Item
    status: Literal["active", "sold", "closed"] = "active"
    days_live: int = Field(default=0, ge=0)
    watchers: int = Field(default=0, ge=0)
    sold_to: str | None = None
    sold_price: float | None = None


class BuyerThreadState(BaseModel):
    """Seller-visible state for one buyer conversation.

    `interested_listing_ids` lets the same buyer create a bundle opportunity without letting buyer
    contexts see each other. The seller can use it; other buyers cannot.
    """

    thread_id: str
    listing_id: str
    current_offer: float | None = None
    status: Literal["active", "walked", "accepted", "closed"] = "active"
    interested_listing_ids: list[str] = Field(default_factory=list)


class MarketplaceState(BaseModel):
    """One seller portfolio: multiple listings, many active buyer threads."""

    listings: dict[str, ListingState]
    threads: dict[str, BuyerThreadState] = Field(default_factory=dict)
    max_listing_age_days: int = Field(default=30, ge=1)
    inventory_pressure: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_ids(self) -> "MarketplaceState":
        for listing_id, listing in self.listings.items():
            if listing.listing_id != listing_id:
                raise ValueError(f"listing key {listing_id!r} does not match listing_id {listing.listing_id!r}")
        for thread_id, thread in self.threads.items():
            if thread.thread_id != thread_id:
                raise ValueError(f"thread key {thread_id!r} does not match thread_id {thread.thread_id!r}")
            if thread.listing_id not in self.listings:
                raise ValueError(f"thread {thread_id!r} references unknown listing {thread.listing_id!r}")
            unknown_interests = [lid for lid in thread.interested_listing_ids if lid not in self.listings]
            if unknown_interests:
                raise ValueError(f"thread {thread_id!r} references unknown interested listings {unknown_interests!r}")
        return self

    def active_threads_for(self, listing_id: str) -> list[BuyerThreadState]:
        listing = self.listings.get(listing_id)
        if listing is None or listing.status != "active":
            return []
        return [
            t for t in self.threads.values()
            if t.listing_id == listing_id and t.status == "active"
        ]

    def best_offer_for(self, listing_id: str, *, exclude_thread_id: str | None = None) -> float | None:
        offers = [
            t.current_offer for t in self.active_threads_for(listing_id)
            if t.thread_id != exclude_thread_id and t.current_offer is not None
        ]
        return max(offers) if offers else None

    def bundle_opportunity_for(self, thread_id: str) -> float:
        thread = self.threads.get(thread_id)
        if thread is None:
            return 0.0
        active_extra = [
            lid for lid in thread.interested_listing_ids
            if lid != thread.listing_id and self.listings.get(lid) and self.listings[lid].status == "active"
        ]
        return 1.0 if active_extra else 0.0

    def features_for_thread(self, thread_id: str, *, current_ask: float, round_idx: int, max_turns: int) -> Features:
        """Build the seller's per-turn feature vector from portfolio state.

        This keeps the current single-thread policy compatible while giving a future
        MarketplaceDomain the extra BATNA/context signals it needs.
        """
        thread = self.threads[thread_id]
        listing = self.listings[thread.listing_id]
        if listing.status != "active" or thread.status != "active":
            raise ValueError("cannot build pricing features for an inactive listing/thread")
        item = listing.item
        listing_id = thread.listing_id
        best_other_offer = self.best_offer_for(listing_id, exclude_thread_id=thread_id)
        best_offer_gap = 0.0 if best_other_offer is None else (current_ask - best_other_offer) / item.list_price
        reservation_gap = 0.0 if thread.current_offer is None else (current_ask - thread.current_offer) / item.list_price
        return Features(
            margin_ratio=item.margin_ratio,
            reservation_gap=reservation_gap,
            turn_frac=round_idx / max(max_turns, 1),
            active_buyers=float(max(0, len(self.active_threads_for(listing_id)) - 1)),
            best_offer_gap=best_offer_gap,
            listing_age=listing.days_live / self.max_listing_age_days,
            inventory_pressure=self.inventory_pressure,
            bundle_opportunity=self.bundle_opportunity_for(thread_id),
        )

    def commit_sale(self, listing_id: str, thread_id: str, price: float) -> "MarketplaceState":
        """Return a copy with one listing sold; prevents double-selling the same listing."""
        listing = self.listings[listing_id]
        if listing.status != "active":
            raise ValueError(f"listing {listing_id} is not active")
        thread = self.threads.get(thread_id)
        if thread is None:
            raise ValueError(f"thread {thread_id} does not exist")
        if thread.listing_id != listing_id:
            raise ValueError(f"thread {thread_id} does not belong to listing {listing_id}")
        if thread.status != "active":
            raise ValueError(f"thread {thread_id} is not active")
        item = listing.item
        if price < item.floor_price:
            raise ValueError("cannot commit a sale below the listing floor")

        listings = {k: v.model_copy(deep=True) for k, v in self.listings.items()}
        threads = {k: v.model_copy(deep=True) for k, v in self.threads.items()}
        listings[listing_id] = listing.model_copy(
            update={"status": "sold", "sold_to": thread_id, "sold_price": price}
        )
        for tid, thread in threads.items():
            if thread.listing_id == listing_id:
                threads[tid] = thread.model_copy(update={"status": "accepted" if tid == thread_id else "closed"})
        return self.model_copy(update={"listings": listings, "threads": threads})
