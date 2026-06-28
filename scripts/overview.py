#!/usr/bin/env python3
"""Lord-mode overview — aggregate stats across all recorded negotiation episodes.

Reads the `source=human` games that `scripts/play.py` persists to `data/human_episodes/` and
rolls them up into one read-only scoreboard: close rate, surplus distribution, per-bucket
performance (weakest first), and the buckets where real buyers beat the agent — i.e. the
proposer-fuel targets for what to learn next. No LLM, no API, fast.

    uv run python scripts/overview.py                 # the pretty god-view
    uv run python scripts/overview.py --bucket mid/unknown
    uv run python scripts/overview.py --json          # machine-readable aggregate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean, median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `gambit` importable

DEFAULT_DIR = Path("data/human_episodes")


def _money(value: float | int | None) -> str:
    """Human money formatting: whole dollars when whole, cents when cents matter (matches play.py)."""
    if value is None:
        return "—"
    amount = round(float(value), 2)
    if abs(amount - round(amount)) < 0.005:
        return f"${amount:,.0f}"
    return f"${amount:,.2f}"


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


def _f(x: float | None) -> str:
    return "—" if x is None else f"{x:+.3f}"


def _num(v, cast, default=None):
    """Tolerant cast: missing/None/garbage → default."""
    try:
        return cast(v)
    except (TypeError, ValueError):
        return default


def _item_name(rec: dict) -> str:
    ep = rec.get("episode") or {}
    item = ep.get("item") or {}
    return item.get("name") or "?"


def _load(d: Path) -> list[dict]:
    recs: list[dict] = []
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text())
        except Exception as e:  # noqa: BLE001 — skip a bad/partial file, never crash the rollup
            print(f"  ! skipping {f.name}: {e}", file=sys.stderr)
            continue
        if isinstance(data, dict):
            recs.append(data)
    return recs


def _aggregate(recs: list[dict]) -> dict:
    n = len(recs)
    deals = [r for r in recs if r.get("deal")]
    deal_surplus = [s for r in deals if (s := _num(r.get("surplus"), float)) is not None]
    rewards = [v for r in recs if (v := _num(r.get("reward"), float)) is not None]
    turns = [v for r in recs if (v := _num(r.get("turns"), int)) is not None]
    viols = [_num(r.get("viol"), int, 0) for r in recs]
    walked = sum(1 for r in recs if not r.get("deal") and "walk" in str(r.get("reason", "")).lower())

    top = {
        "episodes": n,
        "deals": len(deals),
        "close_rate": (len(deals) / n) if n else None,
        "no_deal_rate": ((n - len(deals)) / n) if n else None,
        "walk_rate": (walked / n) if n else None,
        "mean_surplus_deals": mean(deal_surplus) if deal_surplus else None,
        "median_surplus_deals": median(deal_surplus) if deal_surplus else None,
        "mean_reward": mean(rewards) if rewards else None,
        "mean_turns": mean(turns) if turns else None,
        "total_viol": sum(viols),
    }

    # --- per-bucket rollup (weakest mean-surplus first) ---
    by: dict[str, list[dict]] = {}
    for r in recs:
        by.setdefault(str(r.get("bucket", "?")), []).append(r)
    buckets = []
    for key, group in by.items():
        gdeals = [r for r in group if r.get("deal")]
        gsurp = [s for r in gdeals if (s := _num(r.get("surplus"), float)) is not None]
        greward = [v for r in group if (v := _num(r.get("reward"), float)) is not None]
        buckets.append({
            "bucket": key,
            "n": len(group),
            "deals": len(gdeals),
            "close_rate": (len(gdeals) / len(group)) if group else None,
            "mean_surplus": mean(gsurp) if gsurp else None,
            "mean_reward": mean(greward) if greward else None,
            "viol": sum(_num(r.get("viol"), int, 0) for r in group),
        })
    # weakest (lowest mean surplus) first; buckets with no deals sort last
    buckets.sort(key=lambda b: (b["mean_surplus"] is None, b["mean_surplus"] if b["mean_surplus"] is not None else 0.0))

    # --- surplus histogram over closed deals (10 bins, [0,1]) ---
    hist = [0] * 10
    for s in deal_surplus:
        idx = min(9, max(0, int(s * 10)))
        hist[idx] += 1

    # --- weakest buckets with >=1 deal (proposer-fuel targets) ---
    weakest = [b for b in buckets if b["deals"] >= 1][:3]

    # --- recent games (last 5 by ts) ---
    recent = sorted(recs, key=lambda r: str(r.get("ts", "")))[-5:][::-1]
    recent_rows = [{
        "ts": r.get("ts"), "item": _item_name(r), "bucket": r.get("bucket"),
        "deal": bool(r.get("deal")), "price": _num(r.get("price"), float),
        "surplus": _num(r.get("surplus"), float), "reason": r.get("reason"),
    } for r in recent]

    ts_all = sorted(str(r.get("ts", "")) for r in recs if r.get("ts"))
    return {
        "top": top,
        "since": ts_all[0] if ts_all else None,
        "until": ts_all[-1] if ts_all else None,
        "policies": sorted({str(r.get("policy", "?")) for r in recs}),
        "buckets": buckets,
        "histogram": hist,
        "weakest": weakest,
        "recent": recent_rows,
    }


def _render(agg: dict) -> None:
    t = agg["top"]
    rule = "─" * 64
    print("\nGambit — negotiation overview (source=human)")
    print(rule)
    print(f"Episodes: {t['episodes']}   "
          f"Window: {(agg['since'] or '—')[:10]} → {(agg['until'] or '—')[:10]}")
    print(f"Policies seen: {', '.join(agg['policies']) or '—'}")

    print("\nTop line")
    print(rule)
    print(f"Close rate     {_pct(t['close_rate'])}   ({t['deals']}/{t['episodes']} deals)")
    print(f"No-deal/walk   {_pct(t['no_deal_rate'])} no-deal · {_pct(t['walk_rate'])} walked")
    print(f"Surplus (deals) mean {_money_surplus(t['mean_surplus_deals'])}  "
          f"median {_money_surplus(t['median_surplus_deals'])}")
    turns = "—" if t["mean_turns"] is None else f"{t['mean_turns']:.1f}"
    print(f"Mean reward    {_f(t['mean_reward'])}    Mean turns  {turns}")
    viol = t["total_viol"]
    print(f"Integrity      {'CLEAN (viol=0)' if viol == 0 else f'⚠ {viol} VIOLATION(S) — investigate'}")

    print("\nPer-bucket (weakest surplus first — where to improve)")
    print(rule)
    print(f"{'bucket':<18}{'n':>4}{'close':>8}{'surplus':>10}{'reward':>9}{'viol':>6}")
    for b in agg["buckets"]:
        surp = "—" if b["mean_surplus"] is None else f"{b['mean_surplus']:.3f}"
        print(f"{b['bucket']:<18}{b['n']:>4}{_pct(b['close_rate']):>8}{surp:>10}{_f(b['mean_reward']):>9}{b['viol']:>6}")

    print("\nSurplus distribution (closed deals)")
    print(rule)
    _histogram(agg["histogram"])

    if agg["weakest"]:
        print("\nWeakest buckets — proposer-fuel targets (real buyers beat the agent here)")
        print(rule)
        for b in agg["weakest"]:
            print(f"  • {b['bucket']:<18} mean surplus {b['mean_surplus']:.3f} over {b['deals']} deal(s) "
                  f"— learn to hold more here")

    if agg["recent"]:
        print("\nRecent games")
        print(rule)
        for r in agg["recent"]:
            when = (r["ts"] or "")[:16].replace("T", " ")
            outcome = f"deal {_money(r['price'])} (surplus {r['surplus']:.2f})" if r["deal"] \
                else f"no deal ({r['reason'] or '—'})"
            print(f"  {when:<17}{r['item'][:30]:<31}{outcome}")
    print()


def _money_surplus(x: float | None) -> str:
    """Surplus is a 0..1 ratio, not money — render as a fixed-point ratio."""
    return "—" if x is None else f"{x:.3f}"


def _histogram(hist: list[int]) -> None:
    peak = max(hist) if hist else 0
    if peak == 0:
        print("  (no closed deals yet)")
        return
    width = 40
    for i, count in enumerate(hist):
        lo, hi = i / 10, (i + 1) / 10
        bar = "█" * int(round(count / peak * width)) if count else ""
        print(f"  {lo:.1f}–{hi:.1f} {count:>3} |{bar}")


def main() -> int:
    p = argparse.ArgumentParser(description="Aggregate overview of recorded negotiation episodes")
    p.add_argument("--dir", default=str(DEFAULT_DIR), help="episode directory (default: data/human_episodes)")
    p.add_argument("--bucket", default=None, help="filter to a single situation bucket, e.g. mid/unknown")
    p.add_argument("--json", action="store_true", help="emit the machine-readable aggregate instead")
    args = p.parse_args()

    d = Path(args.dir)
    if not d.exists():
        print(f"no episode directory at {d} — play some games with scripts/play.py first.")
        return 0
    recs = _load(d)
    if args.bucket:
        recs = [r for r in recs if str(r.get("bucket")) == args.bucket]
    if not recs:
        where = f" in bucket {args.bucket!r}" if args.bucket else ""
        print(f"no human episodes yet{where} — play some with scripts/play.py.")
        return 0

    agg = _aggregate(recs)

    if args.json:
        print(json.dumps(agg, indent=2))
    else:
        _render(agg)

    _emit_logfire(agg)
    return 0


def _emit_logfire(agg: dict) -> None:
    """Land the god-view in Logfire as a gambit.kind=overview record (best-effort; never crashes)."""
    from gambit import observability as obs
    obs.configure()
    with obs.job("overview", source="agent", title="overview"):
        t = agg["top"]
        obs.emit("overview", kind="overview",
                 episodes=t["episodes"], deals=t["deals"], close_rate=t["close_rate"],
                 mean_surplus_deals=t["mean_surplus_deals"], mean_reward=t["mean_reward"],
                 total_viol=t["total_viol"], buckets=len(agg["buckets"]),
                 weakest=[b["bucket"] for b in agg["weakest"]])


if __name__ == "__main__":
    raise SystemExit(main())
