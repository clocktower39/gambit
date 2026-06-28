"""Offline self-improvement run — NO LLM, NO labels. Prints the generational curve + transfer.

The claim, made runnable: a frozen deterministic seller whose GLOBAL parametric knob policy is
tuned by a held-out-gated search; verifiable reward + skill climb while viol stays 0 — and the
improvement TRANSFERS to a buyer family it never trained or gated against.

    uv run python scripts/run_offline.py

Honest held-out (build-order #3, docs/eval-plan.md §2):
  - proposal context uses `HeuristicBuyer` over `TRAIN_SEEDS`;
  - the promotion gate uses `HeuristicBuyer` over disjoint `GATE_SEEDS`;
  - then score ONCE on a LOCKED set — the structurally different `FirmAnchorBuyer` family over
    `LOCKED_SEEDS`, which (since each seed GENERATES its own margin/price scenario) are scenarios
    the gate never saw.
The headline is the LOCKED Δ. The `held-out Δ ≤ train Δ` sanity is the signature of genuine
generalization: if the unseen set climbed *faster* than what we tuned on, that would mean an
easier held-out (a leak), not transfer. Numbers are deterministic — illustrative, not live.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `gambit` importable

from gambit.engine import improve, run_batch, summarize  # noqa: E402
from gambit.negotiation import (  # noqa: E402
    FirmAnchorBuyer,
    HeuristicBuyer,
    NegotiationDomain,
    PolicyStore,
    knob_nudges,
)
from gambit.negotiation.policy import KnobPolicy  # noqa: E402
from gambit.negotiation.fixtures import GATE_SEEDS, ITEMS, LOCKED_SEEDS, PERSONAS, TRAIN_SEEDS  # noqa: E402
from gambit.trace import Tracer  # noqa: E402
from gambit.watch import make_emitter  # noqa: E402
from gambit import observability as obs  # noqa: E402


CHECKPOINTS_DIR = Path("checkpoints")


def _save_checkpoint(policy: PolicyStore, name: str = "offline") -> Path:
    """Persist the trained PolicyStore so `scripts/play.py` can face it. Writes
    checkpoints/<name>.json and updates checkpoints/latest.json (the pointer play.py reads by default),
    so 'play the latest trained agent' is automatic after a run."""
    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    blob = policy.model_dump_json(indent=2)
    named = CHECKPOINTS_DIR / f"{name}.json"
    named.write_text(blob)
    (CHECKPOINTS_DIR / "latest.json").write_text(blob)
    return named


def _weak_start(shaped: bool = True) -> PolicyStore:
    # a deliberately poor seller (concedes fast + accepts low) on the chosen substrate
    return PolicyStore(knobs=KnobPolicy(shaped=shaped)).with_base(concession_rate=0.80, accept_ratio=0.80)


def _tune(domain, train, gate, start: PolicyStore, on_event=None):
    return improve(domain, start, knob_nudges, train_cps=train, gate_cps=gate,
                   train_seeds=TRAIN_SEEDS, gate_seeds=GATE_SEEDS,
                   generations=12, min_support=len(gate) * len(GATE_SEEDS), on_event=on_event)


def _changed_coeffs(start: PolicyStore, final: PolicyStore) -> dict[str, dict[str, tuple[float, float]]]:
    out: dict[str, dict[str, tuple[float, float]]] = {}
    for knob, weights in final.knobs.coeffs.items():
        for feature, after in weights.items():
            before = start.knobs.coeffs.get(knob, {}).get(feature, 0.0)
            if abs(after - before) > 1e-9:
                out.setdefault(knob, {})[feature] = (round(before, 3), round(after, 3))
    return out


def _run() -> None:
    trace_id = obs.current_trace_id()                          # the active Logfire run id (shared below)
    domain = NegotiationDomain(ITEMS)
    train = [HeuristicBuyer(p) for p in PERSONAS[:3]]          # proposal context
    gate = [HeuristicBuyer(p) for p in PERSONAS[:3]]           # held-out scenarios for promotion
    locked = [FirmAnchorBuyer(p) for p in PERSONAS[:3]]        # structurally different — never seen by the gate

    def locked_panel(ps: PolicyStore) -> dict:
        return summarize(run_batch(domain, ps, locked, LOCKED_SEEDS))

    # --- live tracing: emit the REAL loop's events to runs/<id>.jsonl for the watch UI ---
    # `logfire_trace_id` links the front-end run to its Logfire trace (the "walk this run" deep-link).
    tracer = Tracer(os.environ.get("GAMBIT_RUN_ID"))
    tracer.emit({"type": "start", "train_family": "HeuristicBuyer", "locked_family": "FirmAnchorBuyer",
                 "generations": 12, "train_seeds": TRAIN_SEEDS, "locked_seeds": LOCKED_SEEDS,
                 "items": [it.name for it in ITEMS], "logfire_trace_id": trace_id})
    emitter = make_emitter(tracer, domain, train, TRAIN_SEEDS)

    # --- the generational curve on the train family (hybrid PolicyStore substrate) ---
    start = _weak_start(shaped=True)
    final, history = _tune(domain, train, gate, start, on_event=emitter)
    print("gen  reward  skill  viol  improved   (promotion gate: HeuristicBuyer on GATE_SEEDS)")
    prev_reward = history[0]["reward"]
    for h in history:                                          # mirror the curve into Logfire metrics + per-gen spans
        with obs.generation(h["gen"]):
            obs.record_reward(h["reward"], job_type="offline-rl", source="agent")
            obs.record_skill(h["skill"], job_type="offline-rl", source="agent")
            if h["gen"] > 0:
                obs.record_gate_delta(h["reward"] - prev_reward, job_type="offline-rl")
                if h.get("improved"):
                    obs.record_promotion(job_type="offline-rl", generation=h["gen"])
            prev_reward = h["reward"]
        print(f"{h['gen']:>3}  {h['reward']:.3f}  {h['skill']:.3f}   {h['viol']}    {h['improved']}")
    print(f"\nstart knobs: {start.knobs.base.model_dump()}")
    print(f"final knobs: {final.knobs.base.model_dump()}")
    print(f"learned coeffs: {_changed_coeffs(start, final)}")

    # --- the headline: transfer to the LOCKED, structurally-different family (scored once) ---
    locked_start, locked_final = locked_panel(start), locked_panel(final)
    gate_d = history[-1]["reward"] - history[0]["reward"]
    locked_d = locked_final["reward"] - locked_start["reward"]
    locked_skill_d = locked_final["skill"] - locked_start["skill"]
    coeff_drift = _changed_coeffs(start, final)
    print("\n--- transfer to the LOCKED held-out (FirmAnchorBuyer, unseen scenarios) ---")
    print(f"locked gen-0 : reward {locked_start['reward']:+.3f}  skill {locked_start['skill']}  viol {locked_start['viol']}")
    print(f"locked final : reward {locked_final['reward']:+.3f}  skill {locked_final['skill']}  viol {locked_final['viol']}")
    print(f"Δreward  gate {gate_d:+.3f}   locked(held-out) {locked_d:+.3f}")
    print(f"Δskill   locked {locked_skill_d:+.3f}")
    transfer_ok = locked_d > 0 and locked_skill_d > 0 and locked_d <= gate_d + 1e-9 and locked_final["viol"] == 0
    print(f"transfer: {'OK' if transfer_ok else 'FAIL'}")

    # close the live trace at the headline (the ablation below is console-only diagnostics)
    tracer.emit({"type": "transfer", "locked_start": locked_start, "locked_final": locked_final,
                 "locked_delta": round(locked_d, 4)})
    tracer.emit({"type": "done", "transfer_ok": transfer_ok})
    tracer.close()

    # --- substrate ablation (eval-plan §N3): diagnostic, not a hard pass criterion. ---
    # `frozen` is the gen-0 no-learning floor. The load-bearing comparison is hybrid-vs-uniform:
    # same optimizer + gate + start knobs, differing only in `shaped`. If hybrid loses to uniform,
    # the coefficient path still may improve over frozen, but situation-keying has not proven its keep.
    frozen = locked_start["reward"]                                         # gen-0 (already computed above)
    uniform_final, _ = _tune(domain, train, gate, _weak_start(shaped=False))  # learn, but one flat knob set
    uniform = locked_panel(uniform_final)["reward"]
    hybrid = locked_final["reward"]                                         # learn + margin-keyed knobs
    coeff_ok = bool(coeff_drift)
    hybrid_lift_ok = hybrid > frozen
    hybrid_beats_uniform = hybrid > uniform
    print("\n--- substrate ablation on the LOCKED held-out (higher = better) ---")
    print(f"frozen (gen-0)          : {frozen:+.3f}")
    print(f"uniform-global (learned): {uniform:+.3f}   lift vs frozen {uniform - frozen:+.3f}")
    print(f"hybrid PolicyStore      : {hybrid:+.3f}   lift vs uniform {hybrid - uniform:+.3f}")
    if hybrid_beats_uniform:
        verdict = "situation-keying earns its keep on this split"
    else:
        verdict = "diagnostic: uniform beats hybrid on this split; do not claim substrate lift yet"
    print(f"verdict: {verdict}")

    saved = _save_checkpoint(final)
    print(f"\nsaved trained policy → {saved}  (+ checkpoints/latest.json)"
          f"\nface it live: uv run python scripts/play.py")

    if not (transfer_ok and coeff_ok and hybrid_lift_ok):
        raise SystemExit(1)


def main() -> None:
    # One Logfire run, sharing the front-end's run id (GAMBIT_RUN_ID) so a Logfire trace and a
    # watch-UI run are the same thing. No-op-safe: unconfigured/offline runs are unaffected.
    obs.configure()
    with obs.job("offline-rl", source="agent",
                 run_id=os.environ.get("GAMBIT_RUN_ID"), checkpoint="offline"):
        _run()


if __name__ == "__main__":
    main()
