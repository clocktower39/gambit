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
    PolicyStore,
    Move,
    NegotiationDomain,
    Outcome,
    audit_episode,
    budget_of,
    reward,
    run_episode,
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
    policy = PolicyStore()
    buyer = HeuristicBuyer(PERSONAS[1])  # Fence-sitter Fran (feasible)
    r1 = domain.rollout(policy, buyer, seed=0)
    r2 = domain.rollout(policy, buyer, seed=0)
    assert isinstance(r1, EpisodeResult)
    assert r1.model_dump() == r2.model_dump()      # deterministic by seed
    assert r1.viol == 0                            # the deterministic policies never cheat
    assert -1.0 <= r1.reward <= 1.0
    assert r1.skill is None or 0.0 <= r1.skill <= 1.0
    assert r1.bucket.endswith("/unknown")


def test_infeasible_buyer_never_deals_below_floor():
    # Tire-kicker Tess: budget below any floor → a deal would require going sub-floor.
    domain = NegotiationDomain(ITEMS)
    policy = PolicyStore()
    tess = HeuristicBuyer(PERSONAS[3])
    for seed in range(len(ITEMS)):
        item = ITEMS[seed % len(ITEMS)]
        assert budget_of(item, tess.persona) < item.floor_price   # infeasible by construction
        r = domain.rollout(policy, tess, seed=seed)
        assert r.viol == 0                  # integrity holds: never sells below floor
        assert r.reward >= 0.0              # no below-floor deal (no -1); walking is neutral


def test_batch_summary_panel():
    domain = NegotiationDomain(ITEMS)
    policy = PolicyStore()
    buyers = [HeuristicBuyer(p) for p in PERSONAS]
    results = run_batch(domain, policy, buyers, seeds=list(range(len(ITEMS))))
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


# --- the non-terminal walk (docs/strategy.md §4.1): a walk is a bluff, not the end ---------------
# The production heuristic/firm-anchor buyers rarely walk, so the mechanic is exercised here with
# scripted stub policies that satisfy the referee's Seller/Buyer protocols.

class _ScriptSeller:
    """Holds its ask, then accepts the standing buyer offer from round 2 on (i.e. on the rebuttal)."""

    def opening(self, item: Item) -> Move:
        return Move(role="seller", action="offer", offer=item.list_price, text="opening")

    def respond(self, item: Item, current_ask: float, buyer_offer: float | None, round_idx: int) -> Move:
        if round_idx >= 2 and buyer_offer is not None:
            return Move(role="seller", action="accept", offer=float(buyer_offer), text="ok, deal")
        return Move(role="seller", action="offer", offer=float(current_ask), text="holding firm")


class _BluffThenSettle:
    """Round 1: put a floor-clearing offer on the table. Round 2: bluff a walk. Then settle."""

    family = "bluff"

    def __init__(self, persona: BuyerPersona):
        self.persona = persona

    def respond(self, item: Item, seller_ask: float, round_idx: int, current_offer: float | None) -> Move:
        if current_offer is None:
            return Move(role="buyer", action="offer", offer=float(item.floor_price + 5), text="my offer")
        if round_idx == 2:
            return Move(role="buyer", action="walk", text="forget it, I'm out")
        return Move(role="buyer", action="accept", offer=float(seller_ask), text="fine, deal")


class _AlwaysWalk:
    """Re-confirms the walk every turn — the genuine no-deal path."""

    family = "walker"

    def __init__(self, persona: BuyerPersona):
        self.persona = persona

    def respond(self, item: Item, seller_ask: float, round_idx: int, current_offer: float | None) -> Move:
        return Move(role="buyer", action="walk", text="not interested")


def test_first_walk_is_non_terminal_and_can_be_salvaged():
    # The bluff: buyer walks once, but the standing offer is preserved and the seller closes on its
    # rebuttal turn. Under the old terminal-walk rule this same script was an irrecoverable no-deal.
    item = _item(floor_price=80, list_price=100, target_price=90)
    ep = run_episode(item, _ScriptSeller(), _BluffThenSettle(BuyerPersona(name="b", budget_ratio=0.95)))
    assert any(m.action == "walk" for m in ep.moves)     # a walk really happened mid-episode
    assert ep.outcome.deal                                # yet the deal still closed (non-terminal)
    assert ep.outcome.price == item.floor_price + 5      # at the buyer's standing pre-walk offer
    assert audit_episode(ep) == [] and reward(ep) == ep.outcome.surplus > 0


def test_second_walk_re_confirms_and_ends_in_no_deal():
    # No bluff to call: a side that walks twice genuinely leaves. No-deal, neutral reward, clean.
    item = _item(floor_price=80, list_price=100, target_price=90)
    ep = run_episode(item, _ScriptSeller(), _AlwaysWalk(BuyerPersona(name="b", budget_ratio=0.95)))
    assert not ep.outcome.deal
    assert ep.outcome.walked_by == "buyer" and "re-confirmed" in ep.outcome.reason
    assert sum(m.action == "walk" for m in ep.moves) == 2   # exactly one rebuttal turn between the walks
    assert audit_episode(ep) == [] and reward(ep) == 0.0


# --- live-agent integrity: an LLM accept must bind to the price on the table, not self-named -------
# (regression for the reward-inflation hole where a model emits action="accept", offer=<inflated>).
# Monkeypatches the agent call so it's deterministic and makes NO API request.

def test_llm_accept_binds_to_table_price(monkeypatch):
    from gambit.negotiation import agents

    item = _item(floor_price=80, list_price=100, target_price=90)
    # the model tries to close at an inflated, self-named price regardless of the table
    monkeypatch.setattr(agents, "_ask",
                        lambda agent, prompt: agents.AgentMove(text="deal!", action="accept", offer=999))

    seller = agents.LLMSeller()
    # buyer's standing offer is 85 → a seller accept closes at 85, not the model's 999
    assert seller.respond(item, current_ask=95, buyer_offer=85, round_idx=2).offer == 85
    # buyer offered above our ask → never close above our own ask
    assert seller.respond(item, current_ask=95, buyer_offer=120, round_idx=2).offer == 95

    buyer = agents.LLMBuyer(BuyerPersona(name="b", budget_ratio=0.95))   # hidden budget 95
    bmv = buyer.respond(item, seller_ask=90, round_idx=2, current_offer=80)
    assert bmv.action == "accept" and bmv.offer == 90                    # accept = yes at the seller's ask
    # an accept the model names above budget is capped by the reservation rail, never exceeds budget
    bmv2 = buyer.respond(item, seller_ask=200, round_idx=2, current_offer=80)
    assert bmv2.offer <= 95
