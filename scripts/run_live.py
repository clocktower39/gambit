"""Live negotiation run — REAL MiniMax-M3 agents + live Tier-2 verifier + (optional) Gemini lessons.

Unlike run_offline.py (deterministic, no LLM), this drives the actual typed M3 seller/buyer through
the SAME referee (`run_episode`, incl. the non-terminal walk) + verifiable reward + Tier-1 audit,
then runs the live Tier-2 verifier on every episode. If GEMINI_API_KEY is set, it also runs ONE
Gemini-proposed lesson generation on the weakest bucket and re-plays it with the lesson injected
into the seller — the actual textual self-improvement channel, end to end.

    uv run python scripts/run_live.py                       # M3 self-play + verifier (2 scenarios)
    uv run python scripts/run_live.py --seeds 0 1 2 --buyer heuristic
    uv run python scripts/run_live.py --gemini              # + one live Gemini lesson generation

Needs MINIMAX_API_KEY (agents + verifier). The --gemini step needs GEMINI_API_KEY. Real API spend.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `gambit` importable

from gambit.negotiation import NegotiationDomain, PolicyStore, audit_episode, reward, run_episode, situation_key  # noqa: E402
from gambit.negotiation.agents import LLMBuyer, LLMSeller  # noqa: E402
from gambit.negotiation.fixtures import ITEMS, PERSONAS  # noqa: E402
from gambit.negotiation.verifier import QLABEL, verify_episode  # noqa: E402
from gambit.settings import settings  # noqa: E402


def _play(domain, seller, buyer, seed: int, *, show_transcript: bool) -> dict:
    """One live episode → its scored record (reward/viol + Tier-2 verdict), timed."""
    item = domain.scenario(seed)
    t0 = time.perf_counter()
    ep = run_episode(item, seller, buyer, domain.max_turns)
    dt = time.perf_counter() - t0
    o = ep.outcome
    rec = {
        "seed": seed, "bucket": situation_key(item),
        "reward": reward(ep), "viol": len(audit_episode(ep)),
        "deal": o.deal, "price": o.price, "reason": o.reason,
        "skill": (o.skill if (o and o.deal) else None), "ep": ep, "secs": dt,
    }
    rec["verdict"] = verify_episode(ep)            # live Tier-2 audit (degrades to deterministic on failure)
    if show_transcript:
        print(ep.transcript())
    v = rec["verdict"]
    flags = v["flags"]
    flagtxt = "clean" if not flags else "FLAGS: " + ", ".join(QLABEL.get(f, f) for f in flags)
    print(f"  seed {seed} [{rec['bucket']}] {buyer.family:>9} → "
          f"deal={o.deal} price={o.price} reward={rec['reward']:+.3f} viol={rec['viol']} "
          f"verifier[{v.get('mode', '?')}]:{flagtxt}  ({dt:.0f}s · {rec['reason']})")
    return rec


def _panel(label: str, recs: list[dict]) -> None:
    n = len(recs)
    deals = sum(r["deal"] for r in recs)
    mean_reward = sum(r["reward"] for r in recs) / n if n else 0.0
    viol = sum(r["viol"] for r in recs)
    flagged = sum(1 for r in recs if r["verdict"]["flags"])
    print(f"\n[{label}] n={n}  deals={deals}/{n}  mean_reward={mean_reward:+.3f}  "
          f"Tier-1 viol={viol}  Tier-2 flagged={flagged}/{n}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1])
    ap.add_argument("--buyer", choices=["llm", "heuristic"], default="llm")
    ap.add_argument("--gemini", action="store_true", help="run one live Gemini lesson generation on the weakest bucket")
    args = ap.parse_args()

    if not settings.minimax_api_key:
        print("MINIMAX_API_KEY not set — add it to .env and rerun.")
        return

    domain = NegotiationDomain(ITEMS)
    seller = LLMSeller(name="m3-seller")
    if args.buyer == "llm":
        buyers = [LLMBuyer(PERSONAS[1])]              # one M3 buyer persona (self-play)
    else:
        from gambit.negotiation import HeuristicBuyer
        buyers = [HeuristicBuyer(PERSONAS[1])]

    print(f"=== LIVE: M3 seller vs {args.buyer} buyer · seeds {args.seeds} ===")
    recs = [_play(domain, seller, b, s, show_transcript=(i == 0))
            for i, (s, b) in enumerate((s, b) for s in args.seeds for b in buyers)]
    _panel("baseline (no lesson)", recs)

    if not args.gemini:
        print("\n(skip Gemini lesson generation — pass --gemini to run it)")
        return

    # --- one live Gemini lesson generation on the weakest bucket, then re-play with it injected ---
    if not settings.gemini_api_key:
        print("\nGEMINI_API_KEY is empty — add it to .env to run the Gemini lesson step.")
        return
    from collections import defaultdict

    from gambit.optimizer_gemini import AntigravityOptimizer

    # weakest bucket by MEAN reward (not the single worst episode) — consistent with how perf and the
    # before/after delta are computed below, so we target and measure the same thing.
    by_bucket: dict[str, list[dict]] = defaultdict(list)
    for r in recs:
        by_bucket[r["bucket"]].append(r)
    bucket = min(by_bucket, key=lambda b: sum(x["reward"] for x in by_bucket[b]) / len(by_bucket[b]))
    rows = by_bucket[bucket]
    transcripts = [r["ep"].transcript() for r in rows]
    perf = {"mean_reward": sum(r["reward"] for r in rows) / len(rows),
            "viol": sum(r["viol"] for r in rows)}
    print(f"\n=== Gemini lesson generation on weakest bucket '{bucket}' (mean reward {perf['mean_reward']:+.3f}) ===")
    new_store = AntigravityOptimizer().propose(PolicyStore(), bucket, transcripts, perf)
    lesson = new_store.buckets[bucket].lessons[-1].text
    print(f"proposed lesson:\n  {lesson}\n")

    seller_with_lesson = LLMSeller(name="m3-seller+lesson", lessons=[lesson])
    seeds_in_bucket = [r["seed"] for r in recs if r["bucket"] == bucket]
    print(f"=== re-play bucket '{bucket}' seeds {seeds_in_bucket} WITH the lesson ===")
    after = [_play(domain, seller_with_lesson, buyers[0], s, show_transcript=False) for s in seeds_in_bucket]
    before_mean = perf["mean_reward"]
    after_mean = sum(r["reward"] for r in after) / len(after) if after else 0.0
    _panel("with Gemini lesson", after)
    print(f"\nlesson effect on '{bucket}': reward {before_mean:+.3f} → {after_mean:+.3f}  "
          f"Δ {after_mean - before_mean:+.3f}  (single-shot, illustrative — not gated/promoted)")


if __name__ == "__main__":
    main()
