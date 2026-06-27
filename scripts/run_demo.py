#!/usr/bin/env python3
"""Phase-1 demo: run the self-improvement loop, then show the gen-0 vs gen-N
head-to-head against the same buyer.

    python scripts/run_demo.py --offline            # no API key needed
    python scripts/run_demo.py --generations 8      # uses DO Inference if key is set
"""

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Haggle self-improvement demo")
    parser.add_argument("--generations", type=int, default=6)
    parser.add_argument("--turns", type=int, default=6)
    parser.add_argument("--offline", action="store_true", help="force heuristic mode (no API)")
    parser.add_argument("--all-items", action="store_true", help="evaluate on all items x personas")
    args = parser.parse_args()

    if args.offline:
        os.environ["OFFLINE"] = "1"

    # Make the package importable when run from the repo root.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from haggle.config import llm_available
    from haggle.improve_loop import default_pairs, evaluate, head_to_head, holdout_pairs, improve
    from haggle.models import budget_of
    from haggle.personas import ITEMS, PERSONAS

    mode = "DigitalOcean Inference (LLM)" if llm_available() else "offline heuristics"
    print(f"=== Haggle — self-improving negotiator | mode: {mode} ===\n")

    pairs = default_pairs(all_items=True)
    history = improve(generations=args.generations, pairs=pairs, max_turns=args.turns)

    first, last = history[0], history[-1]
    s0, sN = first["summary"], last["summary"]
    print("\n--- improvement ---")
    print(f"score    {s0['score']:.3f} -> {sN['score']:.3f}  (+{sN['score'] - s0['score']:.3f})")
    print(f"close    {s0['close_rate']:.0%} -> {sN['close_rate']:.0%}")
    print(f"skill    {s0['avg_skill']:.2f} -> {sN['avg_skill']:.2f}")

    # Head-to-head on the same item + a feasible, motivated buyer.
    item = ITEMS[0]
    buyer = next(p for p in PERSONAS if p.name == "In-a-hurry Hari")
    ep0, epN = head_to_head(first["strategy"], last["strategy"], item, buyer, max_turns=args.turns)

    print(f"\n--- head-to-head: {item.name} vs {buyer.name} (hidden max ${budget_of(item, buyer):.0f}) ---")
    for label, ep in (("GEN-0 (naive)", ep0), ("GEN-N (self-taught)", epN)):
        o = ep.outcome
        result = f"closed at ${o.price:.0f}" if o.deal else f"no deal ({o.reason})"
        print(f"\n[{label}] {result} in {o.turns} turns")
        print(ep.transcript())

    if ep0.outcome.deal and epN.outcome.deal:
        delta = epN.outcome.price - ep0.outcome.price
        print(f"\n>>> Self-taught agent captured ${delta:+.0f} more from the same buyer.")

    # Held-out generalization: did the gains transfer to buyers never trained on?
    ho = holdout_pairs(all_items=True)
    _, h0 = evaluate(first["strategy"], ho, args.turns)
    _, hN = evaluate(last["strategy"], ho, args.turns)
    print("\n--- held-out buyers (never trained on) ---")
    print(f"score {h0['score']:.3f} -> {hN['score']:.3f}   surplus {h0['avg_surplus']:.2f} -> {hN['avg_surplus']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
