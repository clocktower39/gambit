#!/usr/bin/env python3
"""Harvest — consolidate real human games + their reflections into ranked CANDIDATE LESSONS.

`scripts/play.py` persists each real human-vs-agent game; `scripts/reflect.py` turns ONE game
into per-side candidate lessons; `scripts/overview.py` shows which buckets are weak. This is the
consolidation brick: across MANY games, which lessons keep recurring, how much SUPPORT each has
(distinct games independently suggesting it), and which weak buckets most need them — producing a
clean, deduped, ranked candidate set per situation bucket.

INTEGRITY BOUNDARY (non-negotiable): harvest is a PROPOSER-CONSOLIDATOR, never a selector. It
NEVER promotes, NEVER modifies a PolicyStore, NEVER touches the reward. It only ranks candidate
lessons. Promotion stays with the deterministic held-out A/B gate (the build agent's optimizer).
Honest constraint: human games are unpaired and non-reproducible, so a human-derived lesson is a
*hypothesis* — it still has to clear a reproducible held-out (sim now; a human-holdout online A/B
once volume exists) before it earns a place in the policy. Harvest hands the gate a good shortlist;
it does not decide.

    uv run python scripts/harvest.py                 # rank candidates over all games + reflections
    uv run python scripts/harvest.py --min-support 2 # only lessons >=2 distinct games back
    uv run python scripts/harvest.py --bucket mid/unknown
    uv run python scripts/harvest.py --llm-merge     # merge near-duplicates with the coach model
    uv run python scripts/harvest.py --json          # machine-readable

Reads data/human_episodes/*.json + data/reflections/*.json; writes data/candidate_lessons.json.
No API needed by default; --llm-merge and the Logfire emit are optional.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `gambit` importable

EPISODES_DIR = Path("data/human_episodes")
REFLECTIONS_DIR = Path("data/reflections")
OUT_PATH = Path("data/candidate_lessons.json")
_JACCARD_MERGE = 0.45          # lessons whose token sets overlap at/above this are the "same" lesson
_TOP_PER_BUCKET = 5            # candidates shown per bucket in the digest

_STOP = {
    "the", "a", "an", "to", "of", "and", "or", "you", "your", "it", "is", "for", "with", "that",
    "this", "on", "in", "at", "be", "if", "but", "not", "so", "than", "then", "them", "they",
    "instead", "when", "more", "less", "once", "just", "are", "was", "were", "by", "as", "into",
    "out", "up", "down", "from", "their", "its", "before", "after", "while", "do", "dont", "don't",
}


# --- helpers -------------------------------------------------------------------------------

def _num(v, cast, default=None):
    """Tolerant cast: missing/None/garbage → default."""
    try:
        return cast(v)
    except (TypeError, ValueError):
        return default


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _load_dir(d: Path) -> list[tuple[str, dict]]:
    """All JSON records in a dir as (filename, dict); malformed files are skipped, never fatal."""
    out: list[tuple[str, dict]] = []
    for f in sorted(d.glob("*.json")):
        try:
            data = json.loads(f.read_text())
        except Exception as e:  # noqa: BLE001 — skip a bad/partial file, never crash the rollup
            print(f"  ! skipping {f.name}: {e}", file=sys.stderr)
            continue
        if isinstance(data, dict):
            out.append((f.name, data))
    return out


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9$]+", (s or "").lower()) if len(w) > 2 and w not in _STOP}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# --- per-bucket weakness from episodes -----------------------------------------------------

def _bucket_stats(episodes: list[tuple[str, dict]]) -> dict[str, dict]:
    """Per bucket: n, close rate, mean surplus on deals, realized surplus, and a 0..1 weakness.

    `realized_surplus` = mean over ALL games in the bucket of (surplus if a deal closed, else 0) —
    a no-deal realizes nothing. weakness = 1 - realized_surplus, so a bucket that rarely closes OR
    closes cheap ranks as weak (= most in need of better lessons)."""
    by: dict[str, list[dict]] = {}
    for _, r in episodes:
        by.setdefault(str(r.get("bucket", "?")), []).append(r)
    stats: dict[str, dict] = {}
    for key, group in by.items():
        deals = [r for r in group if r.get("deal")]
        dsurp = [s for r in deals if (s := _num(r.get("surplus"), float)) is not None]
        realized = mean([(_num(r.get("surplus"), float, 0.0) if r.get("deal") else 0.0) or 0.0
                         for r in group]) if group else 0.0
        stats[key] = {
            "n": len(group),
            "deals": len(deals),
            "close_rate": (len(deals) / len(group)) if group else None,
            "mean_surplus_deals": mean(dsurp) if dsurp else None,
            "realized_surplus": realized,
            "weakness": _clamp(1.0 - realized),
        }
    return stats


# --- candidate lessons from reflections ----------------------------------------------------

def _raw_candidates(reflections: list[tuple[str, dict]]) -> dict[tuple[str, str], list[dict]]:
    """Group raw candidate lessons by (bucket, side). Each carries its source episode id."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for fname, rec in reflections:
        bucket = str(rec.get("bucket", "?"))
        src = rec.get("source_file") or fname        # the episode this reflection came from
        for side in ("seller", "buyer"):
            side_rec = rec.get(side) or {}
            lesson = (side_rec.get("candidate_lesson") or "").strip()
            if not lesson:
                continue
            groups.setdefault((bucket, side), []).append({"lesson": lesson, "source": src})
    return groups


def _cluster_lexically(cands: list[dict]) -> list[dict]:
    """Greedy single-pass clustering by token-set Jaccard → merged candidates with SUPPORT =
    number of distinct source episodes. Representative text = the longest variant (most complete)."""
    toks = [_tokens(c["lesson"]) for c in cands]
    clusters: list[list[int]] = []
    for i in range(len(cands)):
        for c in clusters:
            if _jaccard(toks[i], toks[c[0]]) >= _JACCARD_MERGE:
                c.append(i)
                break
        else:
            clusters.append([i])
    merged = []
    for c in clusters:
        variants = [cands[i]["lesson"] for i in c]
        sources = sorted({cands[i]["source"] for i in c})
        rep = max(variants, key=len)
        merged.append({"lesson": rep, "support": len(sources),
                       "source_episode_ids": sources, "variants": variants})
    return merged


def _merge_with_llm(bucket: str, side: str, cands: list[dict]) -> list[dict] | None:
    """Optional: one coach-model call to merge near-duplicates into distinct, support-weighted
    lessons. Returns None on any failure so the caller falls back to lexical clustering."""
    try:
        from pydantic import BaseModel
        from pydantic_ai import Agent
        from gambit.llm import model_for

        class _Merged(BaseModel):
            lesson: str
            covers: list[int]      # indices into the enumerated raw candidates this lesson subsumes

        class _Out(BaseModel):
            lessons: list[_Merged]

        agent = Agent(model_for("verifier"), output_type=_Out, retries=2, system_prompt=(
            "You consolidate raw negotiation 'candidate lessons' that were each drafted from one real "
            "game, for a single situation bucket and side. Merge near-duplicates into a SHORT list of "
            "distinct, operational lessons (one or two sentences each). For each merged lesson, list the "
            "indices of the raw candidates it covers. Do not invent lessons not supported by the inputs; "
            "do not drop a genuinely distinct one. You only propose — a separate gate decides adoption."))
        listing = "\n".join(f"[{i}] {c['lesson']}" for i, c in enumerate(cands))
        out = agent.run_sync(
            f"Bucket {bucket}, {side} side. Merge these raw candidate lessons:\n{listing}").output
        merged = []
        for m in out.lessons:
            idxs = [i for i in m.covers if 0 <= i < len(cands)]
            if not idxs:
                continue
            sources = sorted({cands[i]["source"] for i in idxs})
            merged.append({"lesson": m.lesson.strip(), "support": len(sources),
                           "source_episode_ids": sources,
                           "variants": [cands[i]["lesson"] for i in idxs]})
        return merged or None
    except Exception as e:  # noqa: BLE001 — llm-merge is best-effort; fall back to lexical
        print(f"  ! llm-merge failed for {bucket}/{side} ({e}); using lexical merge", file=sys.stderr)
        return None


# --- the harvest ---------------------------------------------------------------------------

def harvest(episodes_dir: Path, reflections_dir: Path, *, min_support: int,
            bucket_filter: str | None, use_llm: bool) -> dict:
    episodes = _load_dir(episodes_dir) if episodes_dir.exists() else []
    reflections = _load_dir(reflections_dir) if reflections_dir.exists() else []
    if bucket_filter:
        episodes = [(f, r) for f, r in episodes if str(r.get("bucket")) == bucket_filter]
        reflections = [(f, r) for f, r in reflections if str(r.get("bucket")) == bucket_filter]

    stats = _bucket_stats(episodes)
    reflected_sources = {r.get("source_file") or f for f, r in reflections}
    episode_ids = {f for f, _ in episodes}
    without_reflection = sorted(episode_ids - reflected_sources)

    raw = _raw_candidates(reflections)
    buckets: dict[str, dict] = {}
    for (bucket, side), cands in raw.items():
        merged = (_merge_with_llm(bucket, side, cands) if use_llm else None) or _cluster_lexically(cands)
        bstat = stats.get(bucket, {"weakness": 0.5, "n": 0, "deals": 0,
                                   "close_rate": None, "mean_surplus_deals": None, "realized_surplus": None})
        weakness = bstat.get("weakness", 0.5) or 0.5
        for m in merged:
            if m["support"] < min_support:
                continue
            m["side"] = side
            m["score"] = round(m["support"] * weakness, 4)   # weak bucket + recurring lesson = top
            buckets.setdefault(bucket, {"stats": bstat, "candidates": []})["candidates"].append(m)

    for b in buckets.values():
        b["candidates"].sort(key=lambda m: (m["score"], m["support"]), reverse=True)

    # weakest buckets first (then by best candidate score)
    ordered = sorted(buckets.items(),
                     key=lambda kv: (kv[1]["stats"].get("weakness", 0.0),
                                     kv[1]["candidates"][0]["score"] if kv[1]["candidates"] else 0.0),
                     reverse=True)
    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "episodes": len(episodes),
        "reflections": len(reflections),
        "episodes_without_reflection": len(without_reflection),
        "min_support": min_support,
        "merge": "llm" if use_llm else "lexical",
        "buckets": {k: v for k, v in ordered},
    }


# --- rendering + io ------------------------------------------------------------------------

def _render(agg: dict) -> None:
    rule = "─" * 64
    print("\nGambit — candidate lessons (harvested from real games · proposer fuel)")
    print(rule)
    print(f"Episodes: {agg['episodes']}   Reflections: {agg['reflections']}   "
          f"Unreflected: {agg['episodes_without_reflection']}   "
          f"Merge: {agg['merge']}   Min-support: {agg['min_support']}")
    if agg["episodes_without_reflection"]:
        print(f"  ({agg['episodes_without_reflection']} game(s) have no reflection yet — "
              f"run: uv run python scripts/reflect.py --all)")

    if not agg["buckets"]:
        print("\nNo candidate lessons yet at this support threshold.")
        print("Play games (scripts/play.py), reflect (scripts/reflect.py --all), then re-run.")
        return

    for bucket, b in agg["buckets"].items():
        s = b["stats"]
        surp = "—" if s.get("mean_surplus_deals") is None else f"{s['mean_surplus_deals']:.3f}"
        close = "—" if s.get("close_rate") is None else f"{s['close_rate'] * 100:.0f}%"
        print(f"\n{bucket}   (weakness {s.get('weakness', 0):.2f} · {s.get('n', 0)} games · "
              f"close {close} · surplus {surp})")
        print(rule)
        if not b["candidates"]:
            print("  (no candidates over the support threshold)")
            continue
        for m in b["candidates"][:_TOP_PER_BUCKET]:
            print(f"  [{m['side']:>6} · support {m['support']} · score {m['score']:.2f}] {m['lesson']}")
    print("\n(PROPOSER fuel — a shortlist for the held-out A/B gate. Harvest never promotes or selects.)\n")


def _write_out(agg: dict, out_path: Path) -> Path | None:
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(agg, indent=2))
        return out_path
    except Exception as e:  # noqa: BLE001 — never crash on a write error
        print(f"  ! could not write {out_path}: {e}", file=sys.stderr)
        return None


def _emit_logfire(agg: dict) -> None:
    """Land the harvest in Logfire as a gambit.kind=harvest record (best-effort; never crashes)."""
    from gambit import observability as obs
    obs.configure()
    with obs.job("harvest", source="agent", title="harvest"):
        per_bucket = {k: len(v["candidates"]) for k, v in agg["buckets"].items()}
        obs.emit("harvest", kind="harvest",
                 episodes=agg["episodes"], reflections=agg["reflections"],
                 buckets=len(agg["buckets"]), candidates=sum(per_bucket.values()),
                 min_support=agg["min_support"])


def main() -> int:
    p = argparse.ArgumentParser(description="Consolidate human games + reflections into ranked candidate lessons")
    p.add_argument("--episodes-dir", default=str(EPISODES_DIR), help="default data/human_episodes")
    p.add_argument("--reflections-dir", default=str(REFLECTIONS_DIR), help="default data/reflections")
    p.add_argument("--min-support", type=int, default=1, help="min distinct games backing a lesson")
    p.add_argument("--bucket", default=None, help="filter to one situation bucket, e.g. mid/unknown")
    p.add_argument("--llm-merge", action="store_true", help="merge near-duplicates with the coach model")
    p.add_argument("--out", default=str(OUT_PATH), help="candidate-lessons JSON output path")
    p.add_argument("--json", action="store_true", help="print the machine-readable aggregate")
    args = p.parse_args()

    ep_dir, ref_dir = Path(args.episodes_dir), Path(args.reflections_dir)
    if not (ep_dir.exists() and any(ep_dir.glob("*.json"))):
        print(f"No episodes in {ep_dir} — play some games first (scripts/play.py).")
        return 0
    if not (ref_dir.exists() and any(ref_dir.glob("*.json"))):
        print(f"No reflections in {ref_dir} — run: uv run python scripts/reflect.py --all")
        return 0

    agg = harvest(ep_dir, ref_dir, min_support=args.min_support,
                  bucket_filter=args.bucket, use_llm=args.llm_merge)

    if args.json:
        print(json.dumps(agg, indent=2))
    else:
        _render(agg)
        dest = _write_out(agg, Path(args.out))
        if dest:
            print(f"Wrote {dest}  ({sum(len(b['candidates']) for b in agg['buckets'].values())} candidates)")
    _emit_logfire(agg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
