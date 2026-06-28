"""Continuous, checkpointing, multi-generation self-improvement hill-climber (the "league").

This is the headline demo: an M3 seller that measurably improves on a FIXED held-out yardstick
over many generations while integrity (viol) stays at 0 the whole way. It is the multi-generation
successor to `run_live_curve.py` (one Gemini lesson, one A/B) — here the loop runs for hours,
promoting one grounded lesson at a time and checkpointing the honest climbing curve to disk.

The shape of one generation (docs/architecture.md "self-improving optimizer", eval-plan.md §2):

  1. COLLECT  train transcripts on a DIVERSE opponent pool with the CURRENT promoted lessons.
  2. PROPOSE  `--candidates` grounded Gemini lessons for the weakest bucket(s) (vary the bucket).
  3. GATE     paired A/B on the GATE pool: current lessons vs current+candidate. Promote the best
              candidate whose gate mean-reward beats current by > eps AND whose with-lesson viol==0.
  4. SCORE    the FIXED LOCKED yardstick with the new promoted policy — the honest improvement curve.
  5. CHECKPOINT gen_<NNNN>.json + curve.jsonl + a restorable policy_<NNNN>.json dump.

Three DISJOINT scenario windows (each integer seed GENERATES a distinct margin/price scenario via
`domain.scenario`, so disjoint seed ranges == disjoint scenarios): TRAIN proposes, GATE promotes,
LOCKED is the never-trained-on ruler scored EVERY generation with the current promoted policy.

Only the SELLER spends tokens — the opponents are DETERMINISTIC buyer families (HeuristicBuyer /
FirmAnchorBuyer), so the reward signal is reproducible and cheap, and the only stochasticity is M3's
own (low-temperature) sampling. A FRESH `LLMSeller` is built per episode (its per-instance client is
thread-safe), so all episodes of a phase run concurrently on a ThreadPoolExecutor.

Anti-plateau curriculum: after K generations with no promotion, ESCALATE — add a tougher opponent
(a lower-budget persona via the firm-anchor family) to the train+gate pool. The LOCKED yardstick
STAYS FIXED (a constant ruler). When escalation is exhausted and K more gens pass with no progress,
the loop stops and reports a plateau. The loop is robust: one bad generation (an M3/Gemini hiccup)
is logged and skipped rather than killing a multi-hour run.

    # tiny smoke (one generation, end-to-end live):
    uv run python scripts/run_league.py --hours 0.05 --max-gens 1 --pool-n 2 --locked-n 2 \
        --candidates 1 --workers 4 --out /tmp/league_smoke

    # the headline multi-hour run:
    uv run python scripts/run_league.py --hours 3 --out checkpoints/league

Real API spend: M3 seller per turn (every episode) + `--candidates` Gemini calls per generation.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `gambit` importable

from gambit.negotiation import (  # noqa: E402
    FirmAnchorBuyer,
    HeuristicBuyer,
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
from gambit.negotiation.models import BuyerPersona, budget_of  # noqa: E402
from gambit.negotiation.policy import BucketPolicy, Lesson  # noqa: E402
from gambit.optimizer_gemini import AntigravityOptimizer  # noqa: E402
from gambit.settings import settings  # noqa: E402
from gambit import observability as obs  # noqa: E402

_FEASIBLE_HEADROOM = 1.05      # a (seed, opponent) is feasible iff budget clears floor by >=5%
_MAX_PROMPT_TRANSCRIPTS = 8    # cap inlined transcripts so each Gemini prompt stays bounded
_GATE_EPS = 0.01              # candidate must beat current gate mean reward by more than this

# The deterministic opponent FAMILIES (the structural held-out axis: a different behavior class,
# not the same sim re-parameterized). Only the seller is an LLM, so reward stays reproducible.
_FAMILIES = (HeuristicBuyer, FirmAnchorBuyer)

# Curriculum ladder (anti-plateau): progressively tougher buyers (lower budget ceiling, less
# patience). Each escalation step adds the firm-anchor variant of the next persona to the train+gate
# pool. They are mostly feasible only on fatter-margin scenarios (the feasibility filter handles the
# rest), where they squeeze surplus harder — so the seller has to actually get better, not just luck
# into easy deals. The LOCKED yardstick never sees them: it stays the constant ruler.
_ESCALATION_PERSONAS = (
    BuyerPersona(name="Hardliner Hugo", style="Firm low ceiling, won't chase a deal.",
                 budget_ratio=0.82, patience=5, eagerness=0.30),
    BuyerPersona(name="Skinflint Sue", style="Squeezes every dollar, slow to move.",
                 budget_ratio=0.76, patience=4, eagerness=0.25),
    BuyerPersona(name="Granite Gus", style="Anchors hard, rarely budges off it.",
                 budget_ratio=0.72, patience=3, eagerness=0.20),
)


# --- opponent pool & feasible matchups ----------------------------------------------------------

def _build_pool(personas: list[BuyerPersona], level: int) -> list:
    """The active opponent pool: BOTH families × the base feasible personas, plus one tougher
    firm-anchor opponent per escalation `level`. Buyers are deterministic and stateless, so a single
    instance is safe to reuse across all concurrent episodes."""
    pool = [Fam(p) for p in personas for Fam in _FAMILIES]
    pool += [FirmAnchorBuyer(_ESCALATION_PERSONAS[i]) for i in range(min(level, len(_ESCALATION_PERSONAS)))]
    return pool


def _feasible_matchups(domain: NegotiationDomain, pool: list, start: int, count: int,
                       hard_cap: int) -> list[tuple[int, object]]:
    """Scan seeds from `start` (exclusive upper bound `hard_cap` keeps each window disjoint) and
    collect `count` feasible (seed, opponent) matchups, round-robining opponents so both scenarios
    AND opponents vary. A matchup is feasible iff the opponent's hidden budget clears the floor with
    headroom — otherwise the only clean outcome is a walk, which carries no surplus signal."""
    matchups: list[tuple[int, object]] = []
    seed, oi = start, 0
    while len(matchups) < count and seed < hard_cap:
        opp = pool[oi % len(pool)]
        item = domain.scenario(seed)
        if budget_of(item, opp.persona) >= item.floor_price * _FEASIBLE_HEADROOM:
            matchups.append((seed, opp))
            oi += 1
        seed += 1
    return matchups


# --- concurrent episode runner ------------------------------------------------------------------

def _run_matchups(domain: NegotiationDomain, matchups: list[tuple[int, object]],
                  lessons: list[str], workers: int) -> list[dict]:
    """Run every (seed, opponent) matchup concurrently, each with a FRESH per-episode `LLMSeller`
    carrying `lessons` (the seller's per-instance client makes thread-parallel episodes safe)."""

    def work(m: tuple[int, object]) -> dict:
        seed, opp = m
        item = domain.scenario(seed)
        seller = LLMSeller(lessons=lessons, max_turns=domain.max_turns)
        ep = run_episode(item, seller, opp, domain.max_turns)
        o = ep.outcome
        return {
            "seed": seed, "bucket": situation_key(item), "reward": reward(ep),
            "viol": len(audit_episode(ep)), "deal": bool(o and o.deal),
            "skill": (o.skill if (o and o.deal) else None), "transcript": ep.transcript(),
            "opp": opp.persona.name, "family": opp.family,
        }

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, m) for m in matchups]
        for f in as_completed(futs):
            results.append(f.result())
    return results


# --- policy helpers -----------------------------------------------------------------------------

def _all_promoted(store: PolicyStore) -> list[str]:
    """Every promoted lesson across all buckets — the seller carries all of them at once."""
    return [l.text for bp in store.buckets.values() for l in bp.lessons if l.promoted]


def _promote(store: PolicyStore, bucket: str, text: str, delta: float, support: int) -> None:
    """Append the winning candidate as a PROMOTED lesson to its bucket (mutates the live store)."""
    bp = store.buckets.setdefault(bucket, BucketPolicy())
    bp.lessons.append(Lesson(text=text, promoted=True, gate_delta=delta, support=support))


def _mean(xs: list[float]) -> float:
    return statistics.fmean(xs) if xs else 0.0


def _score_locked(results: list[dict]) -> dict:
    """Aggregate one locked-yardstick scan: mean reward, mean skill (deals only), total viol, and
    the per-bucket mean reward."""
    by_bucket: dict[str, list[float]] = defaultdict(list)
    for r in results:
        by_bucket[r["bucket"]].append(r["reward"])
    skills = [r["skill"] for r in results if r["skill"] is not None]
    return {
        "locked_reward": _mean([r["reward"] for r in results]),
        "locked_skill": _mean(skills),
        "locked_viol": sum(r["viol"] for r in results),
        "by_bucket": {b: round(_mean(v), 4) for b, v in sorted(by_bucket.items())},
        "n": len(results),
    }


# --- one generation -----------------------------------------------------------------------------

def _generation(gen: int, domain: NegotiationDomain, store: PolicyStore, opt: AntigravityOptimizer,
                pool: list, locked_matchups: list, args) -> dict:
    """Run ONE generation end-to-end and return its checkpoint dict (also mutates `store` on promote).

    Raises on a fatal hiccup — the caller wraps this in try/except so a single bad generation is
    logged and skipped rather than killing a multi-hour run."""
    current_lessons = _all_promoted(store)

    # 1) COLLECT train transcripts on the active pool with the current promoted lessons.
    train_start, gate_start = TRAIN_SEEDS[0], GATE_SEEDS[0]
    train_matchups = _feasible_matchups(domain, pool, train_start, args.pool_n, gate_start)
    train = _run_matchups(domain, train_matchups, current_lessons, args.workers)

    by_bucket: dict[str, list[dict]] = defaultdict(list)
    for r in train:
        by_bucket[r["bucket"]].append(r)
    # Weakest buckets first — we propose lessons for the worst-performing situations.
    ranked = sorted(by_bucket, key=lambda b: _mean([r["reward"] for r in by_bucket[b]]))

    # 2) PROPOSE up to `--candidates` grounded lessons, varying the target bucket for diversity.
    candidates: list[dict] = []
    for i in range(args.candidates):
        if not ranked:
            break
        target = ranked[i % len(ranked)]
        rows = by_bucket[target]
        transcripts = [r["transcript"] for r in rows][:_MAX_PROMPT_TRANSCRIPTS]
        deal_skills = [r["skill"] for r in rows if r["skill"] is not None]
        perf = {
            "mean_reward": round(_mean([r["reward"] for r in rows]), 4),
            "mean_skill": round(_mean(deal_skills), 4),
            "viol": sum(r["viol"] for r in rows),
        }
        try:
            cand_store = opt.propose(store, target, transcripts, perf)
            text = cand_store.buckets[target].lessons[-1].text
            candidates.append({"bucket": target, "text": text, "perf": perf})
            obs.reflection(bucket=target, seller_lesson=text,
                           surplus=perf["mean_reward"], viol=perf["viol"])
        except Exception as exc:  # noqa: BLE001 — a Gemini hiccup skips this candidate, not the gen
            obs.emit("propose failed for {bucket}: {err}", level="warn", kind="propose_error",
                     bucket=target, err=repr(exc))
            print(f"  [gen {gen}] propose failed for {target}: {type(exc).__name__}: {exc}")

    # 3) GATE: paired A/B on the GATE pool. Run the CURRENT arm once, reuse for every candidate.
    gate_matchups = _feasible_matchups(domain, pool, gate_start, args.pool_n, LOCKED_SEEDS[0])
    promoted = False
    best = {"delta": _GATE_EPS, "bucket": None, "text": None}
    if candidates and gate_matchups:
        cur = _run_matchups(domain, gate_matchups, current_lessons, args.workers)
        cur_mean = _mean([r["reward"] for r in cur])
        for c in candidates:
            cand = _run_matchups(domain, gate_matchups, current_lessons + [c["text"]], args.workers)
            cand_mean = _mean([r["reward"] for r in cand])
            cand_viol = sum(r["viol"] for r in cand)
            delta = cand_mean - cur_mean
            print(f"  [gen {gen}] gate {c['bucket']:<10} Δ={delta:+.3f} "
                  f"(cur {cur_mean:+.3f} → cand {cand_mean:+.3f}) with-viol={cand_viol}")
            # Promote the BEST candidate that clears eps AND keeps integrity (with-lesson viol==0).
            if cand_viol == 0 and delta > best["delta"]:
                best = {"delta": delta, "bucket": c["bucket"], "text": c["text"]}
        if best["bucket"] is not None:
            _promote(store, best["bucket"], best["text"], best["delta"], support=len(gate_matchups))
            promoted = True
            obs.record_gate_delta(best["delta"], job_type="self-play")
            obs.record_promotion(job_type="self-play", generation=gen)
            print(f"  [gen {gen}] PROMOTED → {best['bucket']} (Δ={best['delta']:+.3f}): {best['text'][:90]}")

    # 4) SCORE the FIXED locked yardstick with the (possibly newly) promoted policy.
    locked_lessons = _all_promoted(store)
    locked_results = _run_matchups(domain, locked_matchups, locked_lessons, args.workers)
    sc = _score_locked(locked_results)
    obs.record_surplus(sc["locked_reward"], job_type="self-play", source="agent")
    obs.record_skill(sc["locked_skill"], job_type="self-play", source="agent")

    return {
        "gen": gen,
        "locked_reward": round(sc["locked_reward"], 4),
        "locked_skill": round(sc["locked_skill"], 4),
        "locked_viol": sc["locked_viol"],
        "locked_by_bucket": sc["by_bucket"],
        "locked_n": sc["n"],
        "n_lessons": len(locked_lessons),
        "promoted": promoted,
        "promoted_bucket": best["bucket"] if promoted else None,
        "gate_delta": round(best["delta"], 4) if promoted else 0.0,
        "promoted_lessons": locked_lessons,
        "n_candidates": len(candidates),
    }


# --- checkpoints --------------------------------------------------------------------------------

def _checkpoint(out: Path, ckpt: dict, store: PolicyStore) -> None:
    """Write the per-gen checkpoint, append the curve line, and dump the restorable policy."""
    gen = ckpt["gen"]
    (out / f"gen_{gen:04d}.json").write_text(json.dumps(ckpt, indent=2))
    (out / f"policy_{gen:04d}.json").write_text(json.dumps(store.model_dump(), indent=2))
    with (out / "curve.jsonl").open("a") as fh:
        fh.write(json.dumps(ckpt) + "\n")


# --- main ---------------------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=float, default=3.0, help="wall-clock budget (hours)")
    ap.add_argument("--max-gens", type=int, default=200, help="generation cap")
    ap.add_argument("--pool-n", type=int, default=16, help="feasible train+gate matchups per phase")
    ap.add_argument("--locked-n", type=int, default=16, help="fixed-yardstick feasible matchups")
    ap.add_argument("--candidates", type=int, default=3, help="lessons proposed per generation")
    ap.add_argument("--workers", type=int, default=10, help="concurrent episodes (ThreadPoolExecutor)")
    ap.add_argument("--k", type=int, default=3, help="no-promotion gens before escalating / plateau")
    ap.add_argument("--out", type=str, default="checkpoints/league", help="checkpoint directory")
    args = ap.parse_args()

    if not settings.minimax_api_key:
        print("MINIMAX_API_KEY not set — the M3 seller needs it."); return
    if not settings.gemini_api_key:
        print("GEMINI_API_KEY not set — the optimizer needs it to propose lessons."); return

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    obs.configure()
    with obs.job("self-play", source="agent", run_id=os.environ.get("GAMBIT_RUN_ID"),
                 checkpoint="league", title="league: continuous self-improvement (held-out climb)"):
        _run(args, out)


def _run(args, out: Path) -> None:
    domain = NegotiationDomain(ITEMS)
    store = PolicyStore()
    opt = AntigravityOptimizer()        # constructed once: chains its sandbox state across generations
    base_personas = list(PERSONAS[:3])  # Lex, Fran, Hari are feasible; Tess (PERSONAS[3]) is excluded

    # The LOCKED yardstick is built ONCE from the base pool and never changes — the constant ruler.
    locked_pool = _build_pool(base_personas, level=0)
    locked_matchups = _feasible_matchups(domain, locked_pool, LOCKED_SEEDS[0], args.locked_n,
                                         LOCKED_SEEDS[0] + 1000)
    if not locked_matchups:
        print("No feasible LOCKED matchups found — cannot establish a yardstick."); return

    print(f"=== LEAGUE · continuous self-improvement · {args.workers} workers ===")
    print(f"budget: {args.hours}h / {args.max_gens} gens · pool-n {args.pool_n} · locked-n {len(locked_matchups)} "
          f"· candidates {args.candidates} · curriculum K {args.k}")
    print(f"locked yardstick (FIXED): {[(s, o.persona.name, o.family) for s, o in locked_matchups]}")
    print(f"checkpoints → {out}/\n")

    t0 = time.time()
    deadline = t0 + args.hours * 3600
    level, no_promo, plateau = 0, 0, False
    gen0: dict | None = None
    last: dict | None = None
    total_promotions = 0

    # Graceful stop on Ctrl-C: finish the loop cleanly and write the summary (no half-written gen).
    stop = {"flag": False}
    def _on_sigint(signum, frame):  # noqa: ARG001
        stop["flag"] = True
        print("\n[league] interrupt received — finishing current generation, then summarizing...")
    try:
        signal.signal(signal.SIGINT, _on_sigint)
    except (ValueError, OSError):  # not on the main thread; KeyboardInterrupt fallback below covers it
        pass

    gen = 0
    try:
        while gen < args.max_gens and time.time() < deadline and not stop["flag"]:
            g0 = time.time()
            pool = _build_pool(base_personas, level)
            try:
                ckpt = _generation(gen, domain, store, opt, pool, locked_matchups, args)
            except Exception as exc:  # noqa: BLE001 — one bad gen logs and continues, never kills the run
                obs.emit("generation {gen} failed: {err}", level="error", kind="gen_error",
                         gen=gen, err=repr(exc))
                print(f"[gen {gen}] FAILED ({type(exc).__name__}: {exc}) — skipping, continuing run")
                gen += 1
                continue

            ckpt["elapsed"] = round(time.time() - t0, 1)
            ckpt["t"] = time.time()
            ckpt["opponent_level"] = level
            with obs.generation(gen, checkpoint="league", opponent_level=level):
                obs.emit("league gen {gen}: locked_reward={lr} skill={sk} viol={vi} lessons={nl}",
                         kind="league_gen", gen=gen, lr=ckpt["locked_reward"], sk=ckpt["locked_skill"],
                         vi=ckpt["locked_viol"], nl=ckpt["n_lessons"], promoted=ckpt["promoted"],
                         opponent_level=level)
                # INTEGRITY: the locked yardstick must read viol==0 at every generation.
                if ckpt["locked_viol"] > 0:
                    obs.emit("INTEGRITY BREACH on locked set: viol={vi} at gen {gen}", level="error",
                             kind="integrity", gen=gen, viol=ckpt["locked_viol"])
                    print(f"  [gen {gen}] !!! INTEGRITY BREACH — locked viol={ckpt['locked_viol']} (must be 0) !!!")

            _checkpoint(out, ckpt, store)
            if gen0 is None:
                gen0 = ckpt
            last = ckpt
            if ckpt["promoted"]:
                total_promotions += 1

            print(f"gen {gen:>4} | reward {ckpt['locked_reward']:+.3f} | skill {ckpt['locked_skill']:+.3f} | "
                  f"viol {ckpt['locked_viol']} | lessons {ckpt['n_lessons']} | "
                  f"promoted {'y' if ckpt['promoted'] else 'n'} | lvl {level} | "
                  f"{time.time() - g0:.0f}s | elapsed {ckpt['elapsed'] / 60:.1f}m")

            # CURRICULUM: escalate after K no-promotion gens; plateau once escalation is exhausted.
            if ckpt["promoted"]:
                no_promo = 0
            else:
                no_promo += 1
                if no_promo >= args.k:
                    if level < len(_ESCALATION_PERSONAS):
                        level += 1
                        no_promo = 0
                        opp = _ESCALATION_PERSONAS[level - 1]
                        obs.emit("escalate to level {lvl}: +{opp}", kind="escalate", level=level, opp=opp.name)
                        print(f"  [gen {gen}] ESCALATE → level {level} (added firm-anchor {opp.name})")
                    else:
                        plateau = True
                        print(f"  [gen {gen}] PLATEAU — escalation exhausted and {args.k} more gens with no promotion")
                        break
            gen += 1
    except KeyboardInterrupt:  # fallback if the signal handler couldn't be installed
        print("\n[league] KeyboardInterrupt — summarizing...")

    _summarize(out, gen0, last, total_promotions, store, plateau, time.time() - t0)


def _summarize(out: Path, gen0: dict | None, last: dict | None, promotions: int,
               store: PolicyStore, plateau: bool, elapsed: float) -> None:
    print("\n=== league summary ===")
    if gen0 is None or last is None:
        print("  no generation completed."); return
    dr = last["locked_reward"] - gen0["locked_reward"]
    ds = last["locked_skill"] - gen0["locked_skill"]
    lessons = _all_promoted(store)
    max_viol = max((g.get("locked_viol", 0) for g in (gen0, last)), default=0)
    print(f"  generations completed : {last['gen'] + 1}")
    print(f"  locked reward  : gen0 {gen0['locked_reward']:+.3f} → final {last['locked_reward']:+.3f}  (Δ {dr:+.3f})")
    print(f"  locked skill   : gen0 {gen0['locked_skill']:+.3f} → final {last['locked_skill']:+.3f}  (Δ {ds:+.3f})")
    print(f"  promotions     : {promotions}   total promoted lessons: {len(lessons)}")
    print(f"  locked viol    : gen0 {gen0['locked_viol']}  final {last['locked_viol']}  (must be 0)")
    print(f"  stop reason    : {'plateau' if plateau else 'budget/interrupt'}   elapsed {elapsed / 60:.1f}m")
    if last["locked_viol"] == 0 and dr > 0:
        print("  VERDICT: measurable climb on the FIXED held-out with integrity intact (viol=0).")
    elif last["locked_viol"] != 0:
        print("  VERDICT: integrity breach on the locked set — the climb does not count.")
    else:
        print("  VERDICT: no measurable climb on the locked yardstick this run.")
    print("\n  final promoted lessons:")
    for i, t in enumerate(lessons, 1):
        print(f"    {i}. {t}")

    summary = {
        "generations": last["gen"] + 1,
        "gen0_reward": gen0["locked_reward"], "final_reward": last["locked_reward"], "delta_reward": round(dr, 4),
        "gen0_skill": gen0["locked_skill"], "final_skill": last["locked_skill"], "delta_skill": round(ds, 4),
        "promotions": promotions, "n_lessons": len(lessons), "final_viol": last["locked_viol"],
        "plateau": plateau, "elapsed_min": round(elapsed / 60, 1), "promoted_lessons": lessons,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\n  wrote {out}/summary.json")


if __name__ == "__main__":
    main()
