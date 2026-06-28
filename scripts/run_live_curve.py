"""Rigorous, concurrent, paired LIVE A/B — does a Gemini lesson reliably raise M3 seller surplus?

This is the proper-design (eval-plan.md §2: paired-by-seed + a significance test) successor to the
earlier n=3 single-shot, which was too noisy to read. One Gemini generation, many seeds, repeated,
and run CONCURRENTLY. The policy under test is the M3 seller's TEXTUAL lesson (Gemini's channel);
the counterparty is the deterministic held-out `FirmAnchorBuyer` (only the SELLER spends tokens, so
the reward signal is reproducible and the only stochasticity is M3's own sampling, which the repeats
damp).

Three DISJOINT scenario splits (each integer seed GENERATES a distinct margin/price scenario via
`domain.scenario`, so disjoint seed ranges == disjoint scenarios):

  - TRAIN region  (seeds from TRAIN_SEEDS[0], scanned up to the GATE region)  — propose the lesson,
  - GATE region   (seeds from GATE_SEEDS[0],  scanned up to the LOCKED region) — the A/B gate,
  - LOCKED region (seeds from LOCKED_SEEDS[0], scanned forward)                — the headline transfer.

Only FEASIBLE scenarios are used: a seed is kept only if the held-out buyer's hidden budget clears
the floor with headroom (`budget_of >= floor_price * 1.05`), so a surplus-positive deal is actually
reachable. On an infeasible scenario the only clean outcome is a walk — zero surplus signal, pure
noise in a paired delta — so we filter those out per split (the fixture seed ranges are extended by
scanning forward within each split's disjoint window; documented in `_feasible_seeds`).

The A/B is PAIRED by seed (same seed -> identical scenario in both arms), R repeats per arm, and the
verdict rests on a paired BOOTSTRAP 95% CI on the mean delta plus a hard integrity gate (with-lesson
viol must be 0). If the lesson does not significantly help, the script SAYS SO — noise is not dressed
up as signal.

    uv run python scripts/run_live_curve.py                                    # full run (defaults)
    uv run python scripts/run_live_curve.py --gate-n 2 --locked-n 2 --train-n 2 --repeats 1 --workers 4   # smoke

Real API spend: M3 seller per turn (every episode) + one Gemini call (the single lesson proposal).
"""

from __future__ import annotations

import argparse
import os
import random
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from gambit.negotiation.fixtures import (  # noqa: E402
    GATE_SEEDS,
    ITEMS,
    LOCKED_SEEDS,
    PERSONAS,
    TRAIN_SEEDS,
)
from gambit.negotiation.models import budget_of  # noqa: E402
from gambit.optimizer_gemini import AntigravityOptimizer  # noqa: E402
from gambit.settings import settings  # noqa: E402
from gambit import observability as obs  # noqa: E402

_BOOTSTRAP_RESAMPLES = 2000
_BOOTSTRAP_SEED = 20260628          # fixed so the CI is reproducible run-to-run
_FEASIBLE_HEADROOM = 1.05           # budget must clear floor by >=5% for a surplus-positive deal
_MAX_PROMPT_TRANSCRIPTS = 8         # cap inlined transcripts so the Gemini prompt stays bounded


# --- feasible-scenario selection (disjoint per split) -------------------------------------------

def _feasible_seeds(domain, buyer, start: int, count: int, hard_cap: int) -> list[int]:
    """Scan seeds from `start` and collect the first `count` FEASIBLE ones (exclusive upper bound
    `hard_cap` keeps each split inside its own disjoint window). A seed is feasible iff the held-out
    buyer can transact above floor with headroom — otherwise the only clean outcome is a walk and the
    paired delta gets no surplus signal from it."""
    persona = buyer.persona
    seeds: list[int] = []
    seed = start
    while len(seeds) < count and seed < hard_cap:
        item = domain.scenario(seed)
        if budget_of(item, persona) >= item.floor_price * _FEASIBLE_HEADROOM:
            seeds.append(seed)
        seed += 1
    if len(seeds) < count:
        raise SystemExit(
            f"Only found {len(seeds)} feasible seeds in [{start}, {hard_cap}); need {count}. "
            f"Lower the -n for this split or widen its window."
        )
    return seeds


# --- concurrent episode runner ------------------------------------------------------------------

def _run_jobs(domain, jobs: list[dict], buyer, workers: int) -> list[dict]:
    """Run each job (one full `run_episode` with a FRESH per-job LLMSeller) concurrently.

    The seller carries a fresh per-instance client, so thread-parallel episodes are safe; the buyer
    is deterministic and stateless across episodes. Returns one result record per job."""

    def work(job: dict) -> dict:
        item = domain.scenario(job["seed"])
        seller = LLMSeller(lessons=job["lessons"], max_turns=domain.max_turns)
        t0 = time.perf_counter()
        ep = run_episode(item, seller, buyer, domain.max_turns)
        return {
            "seed": job["seed"], "arm": job["arm"], "rep": job["rep"],
            "bucket": situation_key(item), "reward": reward(ep),
            "viol": len(audit_episode(ep)), "transcript": ep.transcript(),
            "secs": time.perf_counter() - t0,
        }

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, j) for j in jobs]
        for f in as_completed(futs):
            results.append(f.result())
    return results


def _paired_ab(domain, seeds: list[int], lesson_arm: list[str], buyer, repeats: int,
               workers: int) -> dict[int, dict]:
    """Run the paired A/B over `seeds`: 'without' (no lessons) vs 'with' (`lesson_arm`), R repeats
    each, all episodes concurrent. Returns per-seed aggregates keyed by seed."""
    jobs: list[dict] = []
    for seed in seeds:
        for rep in range(repeats):
            jobs.append({"seed": seed, "rep": rep, "arm": "without", "lessons": []})
            jobs.append({"seed": seed, "rep": rep, "arm": "with", "lessons": lesson_arm})
    results = _run_jobs(domain, jobs, buyer, workers)

    by_seed_arm: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for r in results:
        by_seed_arm[(r["seed"], r["arm"])].append(r)

    agg: dict[int, dict] = {}
    for seed in seeds:
        wo, wi = by_seed_arm[(seed, "without")], by_seed_arm[(seed, "with")]
        wo_mean = sum(r["reward"] for r in wo) / len(wo)
        wi_mean = sum(r["reward"] for r in wi) / len(wi)
        agg[seed] = {
            "bucket": wo[0]["bucket"],
            "without_mean": wo_mean, "with_mean": wi_mean, "delta": wi_mean - wo_mean,
            "without_viol": sum(r["viol"] for r in wo), "with_viol": sum(r["viol"] for r in wi),
        }
    return agg


# --- pure-Python statistics (no new deps) -------------------------------------------------------

def _bootstrap_ci(deltas: list[float], resamples: int, rng: random.Random) -> tuple[float, float]:
    """Paired bootstrap 95% CI on the MEAN delta: resample the per-seed deltas with replacement
    `resamples` times, take the 2.5th/97.5th percentiles of the resampled means."""
    if not deltas:
        return (0.0, 0.0)
    n = len(deltas)
    means = sorted(
        sum(rng.choice(deltas) for _ in range(n)) / n
        for _ in range(resamples)
    )
    lo = means[int(0.025 * resamples)]
    hi = means[int(0.975 * resamples)]
    return (lo, hi)


def _report_ab(title: str, agg: dict[int, dict], rng: random.Random) -> dict:
    """Print the per-seed table + aggregate stats for one paired A/B and return the summary."""
    seeds = sorted(agg)
    deltas = [agg[s]["delta"] for s in seeds]
    with_viol = sum(agg[s]["with_viol"] for s in seeds)
    without_viol = sum(agg[s]["without_viol"] for s in seeds)

    print(f"\n=== {title} (n={len(seeds)} feasible seeds, paired by seed) ===")
    print("seed  bucket      without   with     delta    viol(wo/wi)")
    for s in seeds:
        a = agg[s]
        print(f"{s:>4}  {a['bucket']:<10}  {a['without_mean']:+.3f}  {a['with_mean']:+.3f}  "
              f"{a['delta']:+.3f}   {a['without_viol']}/{a['with_viol']}")

    mean_d = statistics.fmean(deltas)
    median_d = statistics.median(deltas)
    lo, hi = _bootstrap_ci(deltas, _BOOTSTRAP_RESAMPLES, rng)
    improved = sum(1 for d in deltas if d > 0)
    ci_excludes_0 = lo > 0 or hi < 0

    print(f"\n  mean Δ      {mean_d:+.3f}")
    print(f"  median Δ    {median_d:+.3f}")
    print(f"  95% CI      [{lo:+.3f}, {hi:+.3f}]  (paired bootstrap, {_BOOTSTRAP_RESAMPLES} resamples)")
    print(f"  sign test   {improved}/{len(seeds)} seeds improved")
    print(f"  violations  without={without_viol}  with={with_viol}")
    return {"n": len(seeds), "mean_d": mean_d, "median_d": median_d, "ci": (lo, hi),
            "improved": improved, "with_viol": with_viol, "without_viol": without_viol,
            "ci_excludes_0": ci_excludes_0}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train-n", type=int, default=6, help="feasible seeds to propose the lesson from")
    ap.add_argument("--gate-n", type=int, default=12, help="feasible seeds for the A/B gate")
    ap.add_argument("--locked-n", type=int, default=12, help="feasible seeds for the headline transfer")
    ap.add_argument("--repeats", type=int, default=2, help="repeats per (seed, arm) to damp M3 noise")
    ap.add_argument("--workers", type=int, default=10, help="concurrent episodes (ThreadPoolExecutor)")
    args = ap.parse_args()

    if not settings.minimax_api_key:
        print("MINIMAX_API_KEY not set."); return
    if not settings.gemini_api_key:
        print("GEMINI_API_KEY not set — the A/B needs the Gemini optimizer to propose the lesson."); return

    obs.configure()
    # One self-play A/B run, sharing the front-end's run id (GAMBIT_RUN_ID) so the Logfire trace and the
    # watch-UI run are the same thing — the A/B becomes live-trackable instead of a detached file poll.
    with obs.job("self-play", source="agent", run_id=os.environ.get("GAMBIT_RUN_ID"),
                 checkpoint="live-ab", title="live A/B: Gemini lesson (held-out transfer)"):
        _run(args)


def _run(args) -> None:
    domain = NegotiationDomain(ITEMS)
    buyer = FirmAnchorBuyer(PERSONAS[1])    # the deterministic held-out counterparty (Fence-sitter Fran)
    rng = random.Random(_BOOTSTRAP_SEED)

    # Disjoint windows: scan each split forward from its fixture start, bounded by the next split's
    # start so the three remain disjoint scenarios even after extending past the fixture lists.
    train_start, gate_start, locked_start = TRAIN_SEEDS[0], GATE_SEEDS[0], LOCKED_SEEDS[0]
    train_seeds = _feasible_seeds(domain, buyer, train_start, args.train_n, gate_start)
    gate_seeds = _feasible_seeds(domain, buyer, gate_start, args.gate_n, locked_start)
    locked_seeds = _feasible_seeds(domain, buyer, locked_start, args.locked_n, locked_start + 1000)

    print(f"=== LIVE paired A/B · M3 seller vs {buyer.persona.name} (held-out) · "
          f"R={args.repeats} repeats · {args.workers} workers ===")
    print(f"feasible splits (disjoint): TRAIN {train_seeds} | GATE {gate_seeds} | LOCKED {locked_seeds}")

    # --- 1) propose ONE grounded lesson from TRAIN transcripts (M3 seller, no lessons) ----------
    print(f"\n[propose] collecting TRAIN transcripts on {len(train_seeds)} seeds (no lessons)...")
    train_jobs = [{"seed": s, "rep": r, "arm": "train", "lessons": []}
                  for s in train_seeds for r in range(args.repeats)]
    train_results = _run_jobs(domain, train_jobs, buyer, args.workers)

    by_bucket: dict[str, list[float]] = defaultdict(list)
    for r in train_results:
        by_bucket[r["bucket"]].append(r["reward"])
    target = min(by_bucket, key=lambda b: statistics.fmean(by_bucket[b]))
    bucket_rewards = [r for r in train_results if r["bucket"] == target]
    transcripts = [r["transcript"] for r in bucket_rewards][:_MAX_PROMPT_TRANSCRIPTS]
    performance = {
        "mean_reward": statistics.fmean(r["reward"] for r in bucket_rewards),
        "viol": sum(r["viol"] for r in bucket_rewards),
    }
    print(f"[propose] weakest bucket '{target}' (mean reward {performance['mean_reward']:+.3f}, "
          f"viol {performance['viol']}); asking Gemini for ONE grounded lesson...")

    opt = AntigravityOptimizer()
    new_store = opt.propose(PolicyStore(), target, transcripts, performance)
    lesson = new_store.buckets[target].lessons[-1].text
    print(f"[propose] Gemini lesson:\n    {lesson}")
    lesson_arm = [lesson]
    obs.reflection(bucket=target, seller_lesson=lesson,
                   surplus=performance["mean_reward"], viol=performance["viol"])

    # --- 2) GATE: paired A/B on the GATE feasible set -------------------------------------------
    print(f"\n[gate] running paired A/B on {len(gate_seeds)} GATE seeds "
          f"({len(gate_seeds) * args.repeats * 2} episodes)...")
    gate_agg = _paired_ab(domain, gate_seeds, lesson_arm, buyer, args.repeats, args.workers)
    gate = _report_ab("GATE", gate_agg, rng)

    helps = gate["mean_d"] > 0 and gate["ci"][0] > 0 and gate["with_viol"] == 0
    if helps:
        gate_reason = "LESSON HELPS — mean Δ>0, bootstrap CI excludes 0, with-lesson viol==0."
    elif gate["with_viol"] != 0:
        gate_reason = f"NOT promotable — with-lesson viol={gate['with_viol']} (integrity gate failed)."
    elif gate["ci"][1] < 0:
        gate_reason = "LESSON HURTS — bootstrap CI is fully below 0 (a reliable regression)."
    else:
        gate_reason = "NOT a reliable improvement — CI includes 0 (indistinguishable from noise)."
    print(f"\n  VERDICT (gate): {gate_reason}")
    obs.record_gate_delta(gate["mean_d"], job_type="self-play")
    obs.emit("ab gate {reason}", kind="ab_gate", split="gate", reason=gate_reason, helps=helps,
             mean_delta=gate["mean_d"], ci_low=gate["ci"][0], ci_high=gate["ci"][1],
             n=gate["n"], improved=gate["improved"], with_viol=gate["with_viol"])

    # --- 3) HEADLINE: same paired A/B on the LOCKED feasible set (never used to pick the lesson) -
    print(f"\n[locked] running paired A/B on {len(locked_seeds)} LOCKED seeds "
          f"({len(locked_seeds) * args.repeats * 2} episodes)...")
    locked_agg = _paired_ab(domain, locked_seeds, lesson_arm, buyer, args.repeats, args.workers)
    locked = _report_ab("LOCKED (headline transfer)", locked_agg, rng)

    locked_helps = locked["mean_d"] > 0 and locked["ci_excludes_0"] and locked["ci"][0] > 0 and locked["with_viol"] == 0
    print(f"\n  VERDICT (locked / headline): "
          + ("TRANSFER CONFIRMED — mean Δ>0, bootstrap CI excludes 0, with-lesson viol==0."
             if locked_helps else
             "NO CREDIBLE TRANSFER — the lesson does not reliably help on the held-out locked set."))
    obs.emit("ab locked {verdict}", kind="ab_locked", split="locked",
             verdict=("transfer" if locked_helps else "no-transfer"), transfer=locked_helps,
             mean_delta=locked["mean_d"], ci_low=locked["ci"][0], ci_high=locked["ci"][1],
             n=locked["n"], improved=locked["improved"], with_viol=locked["with_viol"])

    # --- honest summary -------------------------------------------------------------------------
    print("\n=== summary ===")
    print(f"  GATE   : n={gate['n']}  mean Δ {gate['mean_d']:+.3f}  CI [{gate['ci'][0]:+.3f}, "
          f"{gate['ci'][1]:+.3f}]  improved {gate['improved']}/{gate['n']}  with-viol {gate['with_viol']}")
    print(f"  LOCKED : n={locked['n']}  mean Δ {locked['mean_d']:+.3f}  CI [{locked['ci'][0]:+.3f}, "
          f"{locked['ci'][1]:+.3f}]  improved {locked['improved']}/{locked['n']}  with-viol {locked['with_viol']}")
    print("  caveats: single proposed lesson, one Gemini generation, one held-out buyer family; "
          "LOCKED is the credible transfer number (never used to choose the lesson). "
          "Integrity (with-lesson viol) must read 0 for any positive verdict to count.")


if __name__ == "__main__":
    main()
