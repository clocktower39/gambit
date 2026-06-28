"""Domain-agnostic batch runner + summary panel.

No learning here yet — that's `improve_loop` (the per-bucket held-out A/B), a later
slice. This is the deterministic substrate the whole eval rests on: run a policy
against counterparties over seeds, and summarize. Everything is reproducible by seed.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import mean

from .seam import Counterparty, Domain, EpisodeResult, Policy


def run_batch(
    domain: Domain,
    policy: Policy,
    counterparties: list[Counterparty],
    seeds: list[int],
) -> list[EpisodeResult]:
    """The full cross-product of counterparties × seeds, each a deterministic rollout."""
    return [domain.rollout(policy, cp, s) for cp in counterparties for s in seeds]


def summarize(results: list[EpisodeResult]) -> dict:
    """The metric panel. `reward` is the selector; `skill` is the honest lead metric;
    `viol` MUST be 0 for a gain to count. `buckets` is mean reward per situation cell."""
    if not results:
        return {"n": 0, "viol": 0}
    skills = [r.skill for r in results if r.skill is not None]
    by_bucket: dict[str, list[float]] = defaultdict(list)
    for r in results:
        by_bucket[r.bucket].append(r.reward)
    return {
        "n": len(results),
        "reward": round(mean(r.reward for r in results), 4),    # verifiable selector
        "skill": round(mean(skills), 4) if skills else None,    # honest lead metric (vs hidden budget)
        "viol": sum(r.viol for r in results),                   # integrity — must be 0
        "buckets": {k: round(mean(v), 4) for k, v in sorted(by_bucket.items())},
    }
