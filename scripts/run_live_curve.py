"""Rigorous held-out-gated LIVE self-improvement curve — real M3 seller, real Gemini optimizer.

This is the honest, multi-generation version of run_live.py's n=2 single-shot. The policy being
improved is the M3 seller's TEXTUAL lesson set (Gemini's channel); the counterparty is the
deterministic held-out `FirmAnchorBuyer` family (so only the SELLER spends tokens, and the reward
signal is reproducible). Three disjoint scenario splits, mirroring the offline design:

  - propose from TRAIN_SEEDS transcripts (what Gemini reflects on),
  - PROMOTE on GATE_SEEDS  — a candidate lesson is kept only if mean verifiable reward rises
    with ZERO Tier-1 integrity violations (the gate; never promote a cheat or a regression),
  - headline on LOCKED_SEEDS — scored once, gen-0 (no lessons) vs final (promoted lessons),
    the set the gate never trained on.

KISS gate (per build doctrine): paired held-out reward improvement + a hard viol gate; FDR /
Thompson / demotion deferred until a measured effect needs them. The promoted lessons are injected
into the M3 seller's prompt; the deterministic reward + Tier-1 audit decide everything.

    uv run python scripts/run_live_curve.py                 # defaults: 2 generations, 4 seeds/split
    uv run python scripts/run_live_curve.py --gens 3 --k 4 --verify

Real API spend (M3 seller per turn + one Gemini call per generation). Honest caveats printed.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `gambit` importable

from gambit.negotiation import (  # noqa: E402
    FirmAnchorBuyer,
    NegotiationDomain,
    PolicyStore,
    audit_episode,
    reward,
    run_episode,
    situation_key,
)
from gambit.negotiation.agents import LLMSeller  # noqa: E402
from gambit.negotiation.fixtures import GATE_SEEDS, ITEMS, LOCKED_SEEDS, PERSONAS, TRAIN_SEEDS  # noqa: E402
from gambit.negotiation.policy import BucketPolicy, Lesson  # noqa: E402
from gambit.optimizer_gemini import AntigravityOptimizer  # noqa: E402
from gambit.settings import settings  # noqa: E402


def _play(domain, seeds, lessons, buyers, *, verify) -> list[dict]:
    """Run the M3 seller (carrying `lessons`) against the held-out buyers over `seeds`."""
    recs: list[dict] = []
    for seed in seeds:
        item = domain.scenario(seed)
        seller = LLMSeller(lessons=lessons, max_turns=domain.max_turns)
        for buyer in buyers:
            t0 = time.perf_counter()
            ep = run_episode(item, seller, buyer, domain.max_turns)
            rec = {"seed": seed, "bucket": situation_key(item), "reward": reward(ep),
                   "viol": len(audit_episode(ep)), "ep": ep, "secs": time.perf_counter() - t0}
            if verify:
                from gambit.negotiation.verifier import verify_episode
                rec["verdict"] = verify_episode(ep)
            recs.append(rec)
            v = f" verifier[{rec['verdict']['mode']}]:{'clean' if rec['verdict']['clean'] else rec['verdict']['flags']}" if verify else ""
            print(f"    seed {seed:>3} [{rec['bucket']}] reward={rec['reward']:+.3f} viol={rec['viol']}{v} ({rec['secs']:.0f}s)")
    return recs


def _mean(recs) -> float:
    return sum(r["reward"] for r in recs) / len(recs) if recs else 0.0


def _viol(recs) -> int:
    return sum(r["viol"] for r in recs)


def _weakest_bucket(recs) -> str:
    by: dict[str, list[float]] = defaultdict(list)
    for r in recs:
        by[r["bucket"]].append(r["reward"])
    return min(by, key=lambda b: sum(by[b]) / len(by[b]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gens", type=int, default=2)
    ap.add_argument("--k", type=int, default=4, help="seeds per split")
    ap.add_argument("--verify", action="store_true", help="also run the live Tier-2 verifier each episode")
    args = ap.parse_args()

    if not settings.minimax_api_key:
        print("MINIMAX_API_KEY not set."); return
    if not settings.gemini_api_key:
        print("GEMINI_API_KEY not set — the curve needs the Gemini optimizer."); return

    domain = NegotiationDomain(ITEMS)
    heldout = [FirmAnchorBuyer(PERSONAS[1])]                 # the deterministic held-out counterparty
    train_seeds, gate_seeds, locked_seeds = TRAIN_SEEDS[:args.k], GATE_SEEDS[:args.k], LOCKED_SEEDS[:args.k]
    opt = AntigravityOptimizer()
    promoted: list[str] = []                                 # promoted lesson texts injected into the seller

    print(f"=== LIVE held-out-gated curve · {args.gens} gens · k={args.k} · M3 seller vs FirmAnchorBuyer ===")
    print(f"[gen 0] gate baseline (no lessons) on GATE_SEEDS {gate_seeds}:")
    base_recs = _play(domain, gate_seeds, promoted, heldout, verify=args.verify)
    base = _mean(base_recs)
    curve = [{"gen": 0, "gate_reward": base, "viol": _viol(base_recs), "promoted": 0, "improved": False}]
    print(f"[gen 0] gate_reward={base:+.3f} viol={_viol(base_recs)}")

    for gen in range(1, args.gens + 1):
        print(f"\n[gen {gen}] collect TRAIN transcripts on {train_seeds}:")
        train_recs = _play(domain, train_seeds, promoted, heldout, verify=False)
        target = _weakest_bucket(train_recs)
        transcripts = [r["ep"].transcript() for r in train_recs if r["bucket"] == target]
        perf = {"mean_reward": _mean([r for r in train_recs if r["bucket"] == target]),
                "viol": _viol([r for r in train_recs if r["bucket"] == target])}

        store = PolicyStore()                                # reflect current promoted lessons for the prompt
        if promoted:
            store.buckets[target] = BucketPolicy(lessons=[Lesson(text=t, promoted=True) for t in promoted])
        new_store = opt.propose(store, target, transcripts, perf)
        new_lesson = new_store.buckets[target].lessons[-1].text
        print(f"[gen {gen}] target bucket '{target}' (reward {perf['mean_reward']:+.3f}); Gemini proposed:\n    {new_lesson}")

        candidate = promoted + [new_lesson]
        print(f"[gen {gen}] GATE the candidate on GATE_SEEDS {gate_seeds}:")
        cand_recs = _play(domain, gate_seeds, candidate, heldout, verify=args.verify)
        cand_reward, cand_viol = _mean(cand_recs), _viol(cand_recs)
        improved = cand_reward > base + 1e-9 and cand_viol == 0   # promote only on a clean gain
        if improved:
            promoted, base = candidate, cand_reward
        curve.append({"gen": gen, "target": target, "gate_reward": base, "cand_reward": cand_reward,
                      "viol": cand_viol, "promoted": len(promoted), "improved": improved})
        print(f"[gen {gen}] candidate gate_reward={cand_reward:+.3f} viol={cand_viol} → "
              f"{'PROMOTED' if improved else 'rejected'} (base now {base:+.3f}, {len(promoted)} promoted)")

    print("\n=== gate curve ===")
    print("gen  gate_reward  viol  #lessons  improved")
    for c in curve:
        print(f"{c['gen']:>3}  {c['gate_reward']:+.3f}      {c['viol']}     {c['promoted']}       {c['improved']}")

    # --- headline: LOCKED held-out, scored once (gen-0 no-lessons vs final promoted) ---
    print(f"\n=== headline on LOCKED_SEEDS {locked_seeds} (never gated) ===")
    print("gen-0 (no lessons):")
    lk0 = _play(domain, locked_seeds, [], heldout, verify=args.verify)
    print("final (promoted lessons):")
    lkN = _play(domain, locked_seeds, promoted, heldout, verify=args.verify)
    g, gate_d = curve[-1]["gate_reward"] - curve[0]["gate_reward"], None
    locked_d = _mean(lkN) - _mean(lk0)
    print(f"\nLOCKED reward  gen-0 {_mean(lk0):+.3f} → final {_mean(lkN):+.3f}   Δ {locked_d:+.3f}   "
          f"viol {_viol(lkN)}   (gate Δ {g:+.3f})")
    print(f"transfer: {'POSITIVE' if locked_d > 0 else 'none/!'}   integrity: {'OK' if _viol(lkN) == 0 else 'FAIL'}   "
          f"sanity(locked Δ ≤ gate Δ): {'OK' if locked_d <= g + 1e-9 else 'SUSPECT'}")
    print(f"\n{len(promoted)} lessons promoted across {args.gens} generations. "
          f"Honest caveats: k={args.k} seeds/split (small); gate sees its own seeds (LOCKED is the credible number); "
          f"single held-out family.")


if __name__ == "__main__":
    main()
