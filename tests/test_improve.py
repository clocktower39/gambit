"""Slice 2: the offline self-improvement loop proves the claim — a frozen actuator whose
GLOBAL parametric knob policy is tuned, gated on held-out, with verifiable reward climbing
and viol staying 0. No LLM, no labels.

KISS gate (per build spec): paired held-out A/B + minimum-support + a hard viol gate.
"""

from __future__ import annotations

from gambit.engine import improve, mean_reward, run_batch, summarize
from gambit.engine.improve import _panel
from gambit.negotiation import (
    FirmAnchorBuyer,
    HeuristicBuyer,
    KnobSellerPolicy,
    NegotiationDomain,
    PolicyStore,
    knob_nudges,
    run_episode,
)
from gambit.negotiation.fixtures import ITEMS, LOCKED_SEEDS, PERSONAS, TRAIN_SEEDS
from gambit.negotiation.models import budget_of

SEEDS = list(range(6))


def _domain():
    return NegotiationDomain(ITEMS)


def _buyers():
    # feasible buyers only (drop infeasible Tess so reward signal isn't dominated by no-deals)
    return [HeuristicBuyer(p) for p in PERSONAS[:3]]


def _weak_start() -> PolicyStore:
    # a deliberately poor seller: concedes fast + accepts low → leaves surplus on the table.
    return PolicyStore().with_base(concession_rate=0.80, accept_ratio=0.80)


def test_curve_moves_on_heldout_with_zero_viol():
    domain, buyers = _domain(), _buyers()
    start = _weak_start()
    final, history = improve(
        domain, start, knob_nudges,
        train_cps=buyers, gate_cps=buyers, seeds=SEEDS,
        generations=12, min_support=len(buyers) * len(SEEDS),
    )
    # paired within the SAME run: final gen vs gen-0 baseline (no independent re-measure)
    assert history[-1]["reward"] > history[0]["reward"]   # the claim: held-out reward climbs
    assert all(h["viol"] == 0 for h in history)           # every promotion is integrity-clean
    # monotone non-decreasing by construction (greedy accept only on improvement)
    rewards = [h["reward"] for h in history]
    assert rewards == sorted(rewards)


def test_min_support_blocks_promotion():
    domain, buyers = _domain(), _buyers()
    start = _weak_start()
    before = mean_reward(run_batch(domain, start, buyers, SEEDS))
    final, history = improve(
        domain, start, knob_nudges,
        train_cps=buyers, gate_cps=buyers, seeds=SEEDS,
        generations=5, min_support=10_000,        # impossibly high → nothing can promote
    )
    assert history[-1]["reward"] == _panel(run_batch(domain, start, buyers, SEEDS))["reward"]
    assert final.model_dump() == start.model_dump()   # policy unchanged


def test_improve_is_deterministic():
    domain, buyers = _domain(), _buyers()
    a = improve(domain, _weak_start(), knob_nudges, train_cps=buyers, gate_cps=buyers,
                seeds=SEEDS, generations=8, min_support=len(buyers) * len(SEEDS))
    b = improve(domain, _weak_start(), knob_nudges, train_cps=buyers, gate_cps=buyers,
                seeds=SEEDS, generations=8, min_support=len(buyers) * len(SEEDS))
    assert a[0].model_dump() == b[0].model_dump()   # same final policy
    assert a[1] == b[1]                              # same history


def test_one_knob_sweep_effect_size():
    # measure the effect of a single knob (concession_rate) on held-out reward — sanity that the
    # parametric channel actually carries signal (build spec: measure effect size early).
    domain, buyers = _domain(), _buyers()
    greedy = mean_reward(run_batch(domain, PolicyStore().with_base(concession_rate=0.80), buyers, SEEDS))
    firm = mean_reward(run_batch(domain, PolicyStore().with_base(concession_rate=0.10), buyers, SEEDS))
    assert firm != greedy            # the knob moves the metric (non-trivial effect size)


# --- Slice 3: honest held-out — a structurally different family + a locked, never-gated set -------

def _firm_anchor():
    return [FirmAnchorBuyer(p) for p in PERSONAS[:3]]


def test_firm_anchor_is_a_distinct_structural_family():
    # Not HeuristicBuyer re-parameterized: a different family tag AND different *behavior*. We assert
    # on the behavioral fields (action/offer), not on prose — two families that merely emit different
    # text would be an in-distribution clone (which proves nothing about transfer, eval-plan §2).
    assert FirmAnchorBuyer.family != HeuristicBuyer.family
    domain, policy = _domain(), PolicyStore()

    def trace(buyer, seed):  # the economically meaningful move sequence for one episode
        ep = run_episode(domain.scenario(seed), KnobSellerPolicy(policy.knobs.base), buyer, domain.max_turns)
        return [(m.role, m.action, m.offer) for m in ep.moves]

    diverged = any(
        trace(HeuristicBuyer(p), s) != trace(FirmAnchorBuyer(p), s)
        for p in PERSONAS[:3] for s in TRAIN_SEEDS
    )
    assert diverged


def test_firm_anchor_respects_reservation_and_yields_signal():
    # The held-out family must (a) never breach the hidden budget (the integrity rail holds for a
    # NEW family too) and (b) actually close some deals, or the transfer metric would be all zeros.
    # Uses TRAIN_SEEDS (a smoke check), keeping LOCKED_SEEDS touched only by the one transfer test.
    domain, buyers = _domain(), _firm_anchor()
    panel = summarize(run_batch(domain, PolicyStore(), buyers, TRAIN_SEEDS))
    assert panel["viol"] == 0                 # never sells below floor (audit) — integrity intact
    assert panel["reward"] > 0                 # the family actually closes deals → real signal to transfer to
    for seed in TRAIN_SEEDS:
        item = domain.scenario(seed)
        for p in PERSONAS[:3]:
            buyer, budget = FirmAnchorBuyer(p), budget_of(item, p)
            # every move it can make stays at or below its hidden budget (reservation guard)
            for ask in (item.list_price, budget, item.floor_price):
                for r in (1, p.patience, p.patience + 2):
                    m = buyer.respond(item, float(ask), r, current_offer=float(budget))
                    if m.offer is not None:
                        assert m.offer <= budget + 1e-6


def test_locked_and_train_cover_disjoint_scenarios():
    # Load-bearing: the held-out is real only if the locked seeds generate scenarios the gate never
    # saw. Assert disjointness at the SCENARIO level (not just disjoint integers, which is tautological).
    domain = _domain()
    train_scen = {domain.scenario(s).model_dump_json() for s in TRAIN_SEEDS}
    locked_scen = {domain.scenario(s).model_dump_json() for s in LOCKED_SEEDS}
    assert train_scen.isdisjoint(locked_scen)
    assert len(locked_scen) == len(LOCKED_SEEDS)   # every locked seed is its own distinct scenario


def test_improvement_transfers_to_locked_unseen_family():
    # The whole northstar claim, offline: tune + gate ONLY on the heuristic family over TRAIN_SEEDS,
    # then score once on the structurally different FirmAnchorBuyer family over the LOCKED seeds the
    # gate never saw. Transfer must be positive, integrity-clean, and — the generalization signature
    # — the unseen-family Δ must not exceed the tuned-family Δ (else the held-out was simply easier).
    domain = _domain()
    train, locked = _buyers(), _firm_anchor()
    start = _weak_start()
    final, history = improve(
        domain, start, knob_nudges,
        train_cps=train, gate_cps=train, seeds=TRAIN_SEEDS,
        generations=12, min_support=len(train) * len(TRAIN_SEEDS),
    )

    locked_start = summarize(run_batch(domain, start, locked, LOCKED_SEEDS))
    locked_final = summarize(run_batch(domain, final, locked, LOCKED_SEEDS))
    train_delta = history[-1]["reward"] - history[0]["reward"]
    locked_delta = locked_final["reward"] - locked_start["reward"]

    assert train_delta > 0                                  # the loop actually climbed on what it tuned
    assert locked_final["reward"] > locked_start["reward"]  # and the gain TRANSFERS to the unseen family
    assert locked_final["viol"] == 0                        # transfer is integrity-clean
    assert locked_delta <= train_delta + 1e-9              # generalization, not an easier held-out (leak)
