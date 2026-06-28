"""Foundation slice: the domain-agnostic seam + the deterministic verifiable reward.

These prove the substrate the whole eval rests on (docs/eval-plan.md): a clean deal scores
in [0,1] with viol=0, the integrity guard catches below-floor cheating (reward -1), an
infeasible buyer yields a neutral no-deal, and every rollout is reproducible by seed.
"""

from __future__ import annotations

from gambit.engine import EpisodeResult, run_batch, summarize
from gambit.negotiation import (
    BuyerPersona,
    Episode,
    HeuristicBuyer,
    Item,
    Knobs,
    KnobSellerPolicy,
    Move,
    NegotiationDomain,
    Outcome,
    audit_episode,
    budget_of,
    reward,
    situation_key,
)
from gambit.negotiation.fixtures import ITEMS, PERSONAS


def _item(**kw) -> Item:
    base = dict(name="Widget", list_price=100, target_price=90, floor_price=80)
    base.update(kw)
    return Item(**base)


# --- models / invariants ---------------------------------------------------

def test_item_rejects_floor_above_target():
    import pytest

    with pytest.raises(ValueError):
        _item(floor_price=95, target_price=90)


def test_accept_requires_price():
    import pytest

    with pytest.raises(ValueError):
        Move(role="seller", action="accept", offer=None)


def test_situation_key_drops_price_band():
    # scale-invariant: two items with the SAME margin but very different prices share a bucket
    cheap = _item(list_price=100, target_price=90, floor_price=80)      # margin 0.20 -> mid
    pricey = _item(list_price=1000, target_price=900, floor_price=800)  # margin 0.20 -> mid
    assert situation_key(cheap) == situation_key(pricey) == "mid/unknown"


# --- reward + integrity audit ----------------------------------------------

def test_clean_deal_scores_in_unit_interval_no_viol():
    item = _item(floor_price=80, list_price=100, target_price=90)
    ep = Episode(
        item=item,
        persona=BuyerPersona(name="b", budget_ratio=0.95),
        moves=[
            Move(role="seller", action="offer", offer=100, text="asking 100"),
            Move(role="buyer", action="offer", offer=90, text="90?"),
            Move(role="seller", action="accept", offer=90, text="deal"),
        ],
        outcome=Outcome(deal=True, price=90, turns=1, surplus=0.5, skill=0.66),
    )
    assert audit_episode(ep) == []
    assert reward(ep) == 0.5


def test_below_floor_close_is_caught():
    item = _item(floor_price=80, list_price=100, target_price=90)
    ep = Episode(
        item=item,
        persona=BuyerPersona(name="b", budget_ratio=0.9),
        moves=[Move(role="seller", action="accept", offer=70, text="fine, 70")],
        outcome=Outcome(deal=True, price=70, turns=1, surplus=0.0),
    )
    assert audit_episode(ep)                # non-empty: violation found
    assert reward(ep) == -1.0


def test_hallucinated_price_is_caught():
    item = _item()
    ep = Episode(
        item=item,
        persona=BuyerPersona(name="b", budget_ratio=0.9),
        moves=[Move(role="seller", action="offer", offer=95, text="95")],
        outcome=Outcome(deal=True, price=88, turns=1, surplus=0.4),  # 88 never on the table
    )
    assert any("never appeared" in v for v in audit_episode(ep))
    assert reward(ep) == -1.0


def test_no_deal_is_neutral():
    item = _item()
    ep = Episode(item=item, persona=BuyerPersona(name="b", budget_ratio=0.9),
                 outcome=Outcome(deal=False, turns=6, reason="timeout"))
    assert audit_episode(ep) == []
    assert reward(ep) == 0.0


# --- the seam: a deterministic rollout through the engine -------------------

def test_rollout_is_clean_and_reproducible():
    domain = NegotiationDomain(ITEMS)
    seller = KnobSellerPolicy(Knobs())
    buyer = HeuristicBuyer(PERSONAS[1])  # Fence-sitter Fran (feasible)
    r1 = domain.rollout(seller, buyer, seed=0)
    r2 = domain.rollout(seller, buyer, seed=0)
    assert isinstance(r1, EpisodeResult)
    assert r1.model_dump() == r2.model_dump()      # deterministic by seed
    assert r1.viol == 0                            # the deterministic policies never cheat
    assert -1.0 <= r1.reward <= 1.0
    assert r1.skill is None or 0.0 <= r1.skill <= 1.0
    assert r1.bucket.endswith("/unknown")


def test_infeasible_buyer_never_deals_below_floor():
    # Tire-kicker Tess: budget below any floor → a deal would require going sub-floor.
    domain = NegotiationDomain(ITEMS)
    seller = KnobSellerPolicy(Knobs())
    tess = HeuristicBuyer(PERSONAS[3])
    for seed in range(len(ITEMS)):
        item = ITEMS[seed % len(ITEMS)]
        assert budget_of(item, tess.persona) < item.floor_price   # infeasible by construction
        r = domain.rollout(seller, tess, seed=seed)
        assert r.viol == 0                  # integrity holds: never sells below floor
        assert r.reward >= 0.0              # no below-floor deal (no -1); walking is neutral


def test_batch_summary_panel():
    domain = NegotiationDomain(ITEMS)
    seller = KnobSellerPolicy(Knobs())
    buyers = [HeuristicBuyer(p) for p in PERSONAS]
    results = run_batch(domain, seller, buyers, seeds=list(range(len(ITEMS))))
    panel = summarize(results)
    assert panel["n"] == len(buyers) * len(ITEMS)
    assert panel["viol"] == 0              # whole batch is integrity-clean
    assert -1.0 <= panel["reward"] <= 1.0
    assert panel["skill"] is None or 0.0 <= panel["skill"] <= 1.0
    assert isinstance(panel["buckets"], dict) and panel["buckets"]


def test_skill_is_the_honest_metric_vs_surplus():
    # surplus is vs the floor; skill is vs the hidden budget. With a tight budget the agent
    # can extract most of the buyer's true willingness (high skill) while surplus-vs-floor is modest.
    item = _item(floor_price=80, list_price=100, target_price=90)  # margin denom (list-floor)=20
    ep = Episode(
        item=item, persona=BuyerPersona(name="b", budget_ratio=0.85),  # budget 85
        moves=[Move(role="seller", action="offer", offer=100, text="100"),
               Move(role="buyer", action="offer", offer=84, text="84?"),
               Move(role="seller", action="accept", offer=84, text="deal")],
        outcome=Outcome(deal=True, price=84, turns=1,
                        surplus=(84 - 80) / (100 - 80), skill=(84 - 80) / (85 - 80)),
    )
    assert reward(ep) == ep.outcome.surplus
    assert ep.outcome.skill > ep.outcome.surplus   # 0.8 skill vs 0.2 surplus — extracted 80% of willingness
