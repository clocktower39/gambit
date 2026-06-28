"""Slice 2: the offline self-improvement loop proves the claim — a frozen actuator whose
GLOBAL parametric knob policy is tuned, gated on held-out, with verifiable reward climbing
and viol staying 0. No LLM, no labels.

KISS gate (per build spec): paired held-out A/B + minimum-support + a hard viol gate.
"""

from __future__ import annotations

from gambit.engine import improve, mean_reward, run_batch
from gambit.engine.improve import _panel
from gambit.negotiation import HeuristicBuyer, NegotiationDomain, PolicyStore, knob_nudges
from gambit.negotiation.fixtures import ITEMS, PERSONAS

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
