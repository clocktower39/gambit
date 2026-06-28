"""Read a league run's checkpoints and print the honest climbing curve.

Pairs with `scripts/run_league.py`: it consumes `<out>/curve.jsonl` (one JSON line per generation)
and renders the locked-yardstick history as a table + an ASCII sparkline, the gen-0→latest deltas,
the promotion count, and the final promoted lessons. It LOUDLY flags any generation whose locked
violation count is non-zero — integrity must read 0 the whole way for the climb to count.

    uv run python scripts/review_run.py --out checkpoints/league

Pure standard library (no deps): safe to run mid-flight against a still-growing curve.jsonl.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

_SPARK = " ▁▂▃▄▅▆▇█"   # 9 levels (index 0 is a leading space for the empty/min cell)


def _sparkline(values: list[float]) -> str:
    """Map values onto the 8-level block ramp, scaled to the run's own min..max."""
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = hi - lo
    if span <= 1e-9:
        return _SPARK[4] * len(values)   # flat line — all mid-height
    out = []
    for v in values:
        idx = 1 + int((v - lo) / span * (len(_SPARK) - 2))
        out.append(_SPARK[min(idx, len(_SPARK) - 1)])
    return "".join(out)


def _load(out: Path) -> list[dict]:
    curve = out / "curve.jsonl"
    if not curve.exists():
        raise SystemExit(f"no curve found at {curve} — has the league run produced a generation yet?")
    rows: list[dict] = []
    for line in curve.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass   # tolerate a partially-flushed trailing line on a live run
    rows.sort(key=lambda r: r.get("gen", 0))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=str, default="checkpoints/league", help="league checkpoint directory")
    args = ap.parse_args()

    out = Path(args.out)
    rows = _load(out)
    if not rows:
        raise SystemExit(f"curve at {out}/curve.jsonl is empty — no generations recorded yet.")

    print(f"=== league review · {out} · {len(rows)} generations ===\n")
    print(" gen | locked_reward | locked_skill | viol | lessons | promoted")
    print("-----+---------------+--------------+------+---------+---------")
    dirty: list[int] = []
    for r in rows:
        viol = int(r.get("locked_viol", 0))
        if viol > 0:
            dirty.append(r.get("gen", 0))
        print(f"{r.get('gen', 0):>4} | {r.get('locked_reward', 0.0):>+13.3f} | "
              f"{r.get('locked_skill', 0.0):>+12.3f} | {viol:>4} | {r.get('n_lessons', 0):>7} | "
              f"{'y' if r.get('promoted') else 'n'}")

    rewards = [float(r.get("locked_reward", 0.0)) for r in rows]
    skills = [float(r.get("locked_skill", 0.0)) for r in rows]
    print(f"\n locked_reward  {min(rewards):+.3f} .. {max(rewards):+.3f}")
    print(f"   {_sparkline(rewards)}")
    print(f" locked_skill   {min(skills):+.3f} .. {max(skills):+.3f}")
    print(f"   {_sparkline(skills)}")

    first, latest = rows[0], rows[-1]
    dr = latest.get("locked_reward", 0.0) - first.get("locked_reward", 0.0)
    ds = latest.get("locked_skill", 0.0) - first.get("locked_skill", 0.0)
    promotions = sum(1 for r in rows if r.get("promoted"))
    print(f"\n gen-{first.get('gen', 0)} → gen-{latest.get('gen', 0)}:")
    print(f"   reward  {first.get('locked_reward', 0.0):+.3f} → {latest.get('locked_reward', 0.0):+.3f}  (Δ {dr:+.3f})")
    print(f"   skill   {first.get('locked_skill', 0.0):+.3f} → {latest.get('locked_skill', 0.0):+.3f}  (Δ {ds:+.3f})")
    print(f"   promotions: {promotions}   final lessons: {latest.get('n_lessons', 0)}")

    if dirty:
        print(f"\n  !!! INTEGRITY: locked viol>0 at generations {dirty} — the climb on these does NOT count !!!")
    else:
        print("\n  integrity: locked viol == 0 across every generation.")

    lessons = latest.get("promoted_lessons", [])
    print(f"\n final promoted lessons ({len(lessons)}):")
    for i, t in enumerate(lessons, 1):
        print(f"   {i}. {t}")


if __name__ == "__main__":
    main()
