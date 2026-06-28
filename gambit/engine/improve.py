"""The domain-agnostic generational self-improvement loop.

A proposer (domain-specific) suggests candidate policies; the engine promotes one only if it
beats the current policy on a *held-out* set over the SAME seeds (paired), with enough support
and zero integrity violations. This is the whole claim: a frozen actuator whose policy improves,
verified on counterparties it didn't train against.

KISS (per the build spec): paired held-out A/B + minimum-support + a hard viol gate. FDR /
Thompson / demotion are deliberately deferred until a measured effect justifies them. Nothing
here mentions negotiation — `policy` is opaque; `propose`, `domain`, and the counterparties are
supplied by the caller.
"""

from __future__ import annotations

from statistics import mean
from typing import Callable, Protocol, TypeVar

from .run import run_batch
from .seam import Counterparty, Domain, EpisodeResult

P = TypeVar("P")                     # the policy type — opaque to the engine
Proposer = Callable[[P, list[EpisodeResult]], list[P]]
Metric = Callable[[list[EpisodeResult]], float]


def mean_reward(results: list[EpisodeResult]) -> float:
    """The verifiable selector (deterministic surplus)."""
    return mean(r.reward for r in results) if results else 0.0


def mean_skill(results: list[EpisodeResult]) -> float:
    """The honest scoreboard (extraction vs. hidden budget); reported, not selected on."""
    s = [r.skill for r in results if r.skill is not None]
    return mean(s) if s else 0.0


def _panel(results: list[EpisodeResult]) -> dict:
    return {"reward": round(mean_reward(results), 4), "skill": round(mean_skill(results), 4),
            "viol": sum(r.viol for r in results), "n": len(results)}


def improve(
    domain: Domain,
    policy: P,
    propose: Proposer,
    *,
    train_cps: list[Counterparty],
    gate_cps: list[Counterparty],
    seeds: list[int],
    generations: int = 10,
    min_support: int = 8,
    select: Metric = mean_reward,
) -> tuple[P, list[dict]]:
    """Greedy hill-climb: each generation, accept the best candidate that beats the incumbent on
    the held-out gate (paired over `seeds`), clears `min_support`, and is integrity-clean. The
    held-out gate metric is monotone-non-decreasing by construction; early-stop on a plateau."""

    def gate(p: P) -> list[EpisodeResult]:
        return run_batch(domain, p, gate_cps, seeds)

    base_res = gate(policy)
    base = select(base_res)
    history = [{"gen": 0, "improved": False, **_panel(base_res)}]

    for g in range(1, generations + 1):
        train_res = run_batch(domain, policy, train_cps, seeds)
        best_p: P | None = None
        best_score = base
        best_res: list[EpisodeResult] = base_res
        for cand in propose(policy, train_res):
            res = gate(cand)
            if len(res) < min_support:                 # too little evidence to promote
                continue
            if sum(r.viol for r in res) > 0:           # integrity gate — never promote a cheater
                continue
            score = select(res)
            if score > best_score + 1e-9:              # paired held-out improvement
                best_p, best_score, best_res = cand, score, res
        if best_p is None:                              # plateau → stop (no statistical churn)
            history.append({"gen": g, "improved": False, **_panel(base_res)})
            break
        policy, base, base_res = best_p, best_score, best_res
        history.append({"gen": g, "improved": True, **_panel(base_res)})

    return policy, history
