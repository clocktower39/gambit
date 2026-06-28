"""Offline self-improvement run — NO LLM, NO labels. Prints the generational curve + transfer.

The claim, made runnable: a frozen deterministic seller whose GLOBAL parametric knob policy is
tuned by a held-out-gated search; verifiable reward + skill climb while viol stays 0 — and the
improvement TRANSFERS to a buyer family it never trained or gated against.

    uv run python scripts/run_offline.py

Honest held-out (build-order #3, docs/eval-plan.md §2) — disjoint on BOTH axes:
  - train + gate on the `HeuristicBuyer` family over `TRAIN_SEEDS`;
  - then score ONCE on a LOCKED set — the structurally different `FirmAnchorBuyer` family over
    `LOCKED_SEEDS`, which (since each seed GENERATES its own margin/price scenario) are scenarios
    the gate never saw, with a family it never trained against.
The headline is the LOCKED Δ. The `held-out Δ ≤ train Δ` sanity is the signature of genuine
generalization: if the unseen set climbed *faster* than what we tuned on, that would mean an
easier held-out (a leak), not transfer. Numbers are deterministic — illustrative, not live.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `gambit` importable

from gambit.engine import improve, mean_reward, run_batch, summarize  # noqa: E402
from gambit.negotiation import (  # noqa: E402
    FirmAnchorBuyer,
    HeuristicBuyer,
    NegotiationDomain,
    PolicyStore,
    knob_nudges,
)
from gambit.negotiation.fixtures import ITEMS, LOCKED_SEEDS, PERSONAS, TRAIN_SEEDS  # noqa: E402


def main() -> None:
    domain = NegotiationDomain(ITEMS)
    train = [HeuristicBuyer(p) for p in PERSONAS[:3]]          # the family we tune + gate on
    locked = [FirmAnchorBuyer(p) for p in PERSONAS[:3]]        # structurally different — never seen by the gate
    start = PolicyStore().with_base(concession_rate=0.80, accept_ratio=0.80)  # deliberately weak

    final, history = improve(
        domain, start, knob_nudges,
        train_cps=train, gate_cps=train, seeds=TRAIN_SEEDS,
        generations=12, min_support=len(train) * len(TRAIN_SEEDS),
    )

    print("gen  reward  skill  viol  improved   (train family: HeuristicBuyer)")
    for h in history:
        print(f"{h['gen']:>3}  {h['reward']:.3f}  {h['skill']:.3f}   {h['viol']}    {h['improved']}")
    print(f"\nstart knobs: {start.knobs.base.model_dump()}")
    print(f"final knobs: {final.knobs.base.model_dump()}")

    # The headline: score the LOCKED, structurally-different family ONCE (gen-0 vs final).
    locked_start = summarize(run_batch(domain, start, locked, LOCKED_SEEDS))
    locked_final = summarize(run_batch(domain, final, locked, LOCKED_SEEDS))
    train_d = history[-1]["reward"] - history[0]["reward"]
    locked_d = locked_final["reward"] - locked_start["reward"]

    print("\n--- transfer to the LOCKED held-out family (FirmAnchorBuyer, unseen seeds) ---")
    print(f"locked gen-0 : reward {locked_start['reward']:+.3f}  skill {locked_start['skill']}  viol {locked_start['viol']}")
    print(f"locked final : reward {locked_final['reward']:+.3f}  skill {locked_final['skill']}  viol {locked_final['viol']}")
    print(f"\nΔreward  train {train_d:+.3f}   locked(held-out) {locked_d:+.3f}")
    print(f"transfer: {'POSITIVE' if locked_d > 0 else 'none'}   "
          f"sanity (locked Δ ≤ train Δ): {'OK' if locked_d <= train_d + 1e-9 else 'SUSPECT — easier held-out?'}   "
          f"integrity (locked viol==0): {'OK' if locked_final['viol'] == 0 else 'FAIL'}")


if __name__ == "__main__":
    main()
