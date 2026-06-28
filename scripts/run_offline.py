"""Offline self-improvement run — NO LLM, NO labels. Prints the generational curve.

The claim, made runnable: a frozen deterministic seller whose GLOBAL parametric knob policy is
tuned by a held-out-gated search; verifiable reward + skill climb while viol stays 0.

    uv run python scripts/run_offline.py

Held-out here is in-distribution (same buyer family) until slice 3 adds a structurally-different
family + a locked test set. Treat the numbers as illustrative (deterministic), not a live result.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `gambit` importable

from gambit.engine import improve, mean_reward, run_batch  # noqa: E402
from gambit.negotiation import HeuristicBuyer, NegotiationDomain, PolicyStore, knob_nudges  # noqa: E402
from gambit.negotiation.fixtures import ITEMS, PERSONAS  # noqa: E402


def main() -> None:
    domain = NegotiationDomain(ITEMS)
    buyers = [HeuristicBuyer(p) for p in PERSONAS[:3]]          # feasible families
    seeds = list(range(6))
    start = PolicyStore().with_base(concession_rate=0.80, accept_ratio=0.80)  # deliberately weak

    final, history = improve(
        domain, start, knob_nudges,
        train_cps=buyers, gate_cps=buyers, seeds=seeds,
        generations=12, min_support=len(buyers) * len(seeds),
    )

    print("gen  reward  skill  viol  improved")
    for h in history:
        print(f"{h['gen']:>3}  {h['reward']:.3f}  {h['skill']:.3f}   {h['viol']}    {h['improved']}")
    print(f"\nstart knobs: {start.knobs.base.model_dump()}")
    print(f"final knobs: {final.knobs.base.model_dump()}")
    print(f"\nΔreward {history[-1]['reward'] - history[0]['reward']:+.3f}  "
          f"Δskill {history[-1]['skill'] - history[0]['skill']:+.3f}  (held-out, in-distribution for now)")


if __name__ == "__main__":
    main()
