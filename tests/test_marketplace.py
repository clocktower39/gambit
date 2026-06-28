"""Portfolio-state seam: one seller policy can reason over many buyer threads."""

from __future__ import annotations

import pytest

from gambit.negotiation import BuyerThreadState, Features, Item, KnobPolicy, ListingState, MarketplaceState, PolicyStore


def _item(**kw) -> Item:
    base = dict(name="Widget", list_price=100, target_price=90, floor_price=75)
    base.update(kw)
    return Item(**base)


def _store() -> PolicyStore:
    return PolicyStore(knobs=KnobPolicy()).with_base(
        concession_rate=0.50,
        accept_ratio=0.90,
        walkaway_patience=5,
    )


def test_parallel_buyers_make_the_same_seller_thread_firmer():
    item = _item()
    state = MarketplaceState(
        listings={"l1": ListingState(listing_id="l1", item=item)},
        threads={
            "t1": BuyerThreadState(thread_id="t1", listing_id="l1", current_offer=85),
            "t2": BuyerThreadState(thread_id="t2", listing_id="l1", current_offer=88),
        },
    )
    solo = Features(margin_ratio=item.margin_ratio, reservation_gap=(95 - 85) / item.list_price, turn_frac=1 / 6)
    portfolio = state.features_for_thread("t1", current_ask=95, round_idx=1, max_turns=6)

    solo_knobs = _store().knobs.resolve(solo)
    portfolio_knobs = _store().knobs.resolve(portfolio)

    assert portfolio.active_buyers == 1
    assert portfolio.best_offer_gap == pytest.approx((95 - 88) / item.list_price)
    assert portfolio_knobs.concession_rate < solo_knobs.concession_rate
    assert portfolio_knobs.accept_ratio >= solo_knobs.accept_ratio
    assert portfolio_knobs.walkaway_patience >= solo_knobs.walkaway_patience


def test_stale_inventory_pressure_makes_the_seller_more_flexible():
    item = _item()
    fresh = MarketplaceState(
        listings={"l1": ListingState(listing_id="l1", item=item, days_live=0)},
        threads={"t1": BuyerThreadState(thread_id="t1", listing_id="l1", current_offer=85)},
        inventory_pressure=0.0,
    )
    stale = MarketplaceState(
        listings={"l1": ListingState(listing_id="l1", item=item, days_live=30)},
        threads={"t1": BuyerThreadState(thread_id="t1", listing_id="l1", current_offer=85)},
        inventory_pressure=1.0,
    )

    fresh_knobs = _store().knobs.resolve(fresh.features_for_thread("t1", current_ask=95, round_idx=1, max_turns=6))
    stale_knobs = _store().knobs.resolve(stale.features_for_thread("t1", current_ask=95, round_idx=1, max_turns=6))

    assert stale_knobs.concession_rate > fresh_knobs.concession_rate
    assert stale_knobs.accept_ratio < fresh_knobs.accept_ratio
    assert stale_knobs.walkaway_patience < fresh_knobs.walkaway_patience


def test_commit_sale_prevents_double_sale_and_closes_competing_threads():
    item = _item()
    state = MarketplaceState(
        listings={"l1": ListingState(listing_id="l1", item=item)},
        threads={
            "winner": BuyerThreadState(thread_id="winner", listing_id="l1", current_offer=90),
            "backup": BuyerThreadState(thread_id="backup", listing_id="l1", current_offer=88),
        },
    )

    sold = state.commit_sale("l1", "winner", 90)
    assert sold.listings["l1"].status == "sold"
    assert sold.listings["l1"].sold_to == "winner"
    assert sold.threads["winner"].status == "accepted"
    assert sold.threads["backup"].status == "closed"

    with pytest.raises(ValueError, match="not active"):
        sold.commit_sale("l1", "backup", 88)
    with pytest.raises(ValueError, match="below"):
        state.commit_sale("l1", "winner", 70)


def test_commit_sale_requires_matching_active_thread_and_listing():
    item = _item()
    state = MarketplaceState(
        listings={
            "l1": ListingState(listing_id="l1", item=item),
            "l2": ListingState(listing_id="l2", item=item),
            "closed": ListingState(listing_id="closed", item=item, status="closed"),
        },
        threads={
            "l2-buyer": BuyerThreadState(thread_id="l2-buyer", listing_id="l2", current_offer=90),
            "walked": BuyerThreadState(thread_id="walked", listing_id="l1", current_offer=90, status="walked"),
        },
    )

    with pytest.raises(ValueError, match="does not exist"):
        state.commit_sale("l1", "missing", 90)
    with pytest.raises(ValueError, match="does not belong"):
        state.commit_sale("l1", "l2-buyer", 90)
    with pytest.raises(ValueError, match="not active"):
        state.commit_sale("closed", "l2-buyer", 90)
    with pytest.raises(ValueError, match="not active"):
        state.commit_sale("l1", "walked", 90)


def test_market_features_ignore_inactive_listings_and_threads():
    item = _item()
    state = MarketplaceState(
        listings={"l1": ListingState(listing_id="l1", item=item, status="sold")},
        threads={"t1": BuyerThreadState(thread_id="t1", listing_id="l1", current_offer=90)},
    )

    assert state.active_threads_for("l1") == []
    with pytest.raises(ValueError, match="inactive"):
        state.features_for_thread("t1", current_ask=95, round_idx=1, max_turns=6)


def test_marketplace_state_rejects_inconsistent_external_ids():
    item = _item()
    with pytest.raises(ValueError, match="listing key"):
        MarketplaceState(listings={"l1": ListingState(listing_id="stale", item=item)})
    with pytest.raises(ValueError, match="thread key"):
        MarketplaceState(
            listings={"l1": ListingState(listing_id="l1", item=item)},
            threads={"t1": BuyerThreadState(thread_id="stale", listing_id="l1")},
        )
    with pytest.raises(ValueError, match="unknown listing"):
        MarketplaceState(
            listings={"l1": ListingState(listing_id="l1", item=item)},
            threads={"t1": BuyerThreadState(thread_id="t1", listing_id="missing")},
        )
