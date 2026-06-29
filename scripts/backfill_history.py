"""One-time backfill: pull ALL historical traces from Logfire into the durable on-disk cache.

History is served from `runs/cache/` (see `gambit.logfire_read`) so the app survives restarts and the
aggressive read-API rate limit. New runs land there live (human chats via `runstore`, the poller's
snapshot for everything else), but runs that predate the durable cache live only in Logfire. This
script seeds them — RATE-SAFELY: instead of one query per run (156+ queries → instant throttle), it
pulls every renderable record in a handful of bulk, gated, paginated queries and reconstructs each
run locally. Idempotent: re-running just refreshes the snapshot.

    uv run python scripts/backfill_history.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `gambit` importable

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from gambit import logfire_read as lr  # noqa: E402
from gambit.history import get_history  # noqa: E402

_PAGE = 100            # the Logfire query API hard-caps results at 100 rows; paginate by ts cursor

# Synthetic run-ids that leaked into Logfire from local smoke-tests of the transcript logging — not
# real conversations, so we never restore them (keeps the deploy's Postgres archive clean too).
_SKIP_RUN_IDS = {"t1", "thread-abc"}


async def _bulk_rows(client: httpx.AsyncClient) -> list[dict]:
    """Every renderable record across ALL runs, fetched in gated pages (newest-bounded by ts cursor)."""
    rows: list[dict] = []
    cursor = ""
    while True:
        where = f"attributes->>'gambit.kind' in ({lr._DETAIL_KINDS})"
        if cursor:
            where += f" and start_timestamp > '{cursor}'"
        page = await lr.gated(client, (
            f"select {lr._DETAIL_SELECT} from records where {where} "
            f"order by start_timestamp asc limit {_PAGE}"
        ))
        rows.extend(page)
        print(f"  …pulled {len(rows)} records so far")
        if len(page) < _PAGE:
            break
        cursor = page[-1].get("ts") or ""
        if not cursor:
            break
    return rows


def _summarize(rid: str, rows: list[dict]) -> dict:
    """One run-list row from a run's records — mirrors `logfire_read.fetch_runs`'s per-run summary."""
    job = next((r for r in rows if r.get("kind") == "job"), {})
    any_row = rows[0] if rows else {}
    eps = [r for r in rows if r.get("kind") in ("outcome", "human_episode")]
    metric_rows = [r for r in rows if r.get("kind") == "league_gen"]
    score_rows = eps if eps else metric_rows
    rewards = [v for r in eps if (v := lr._f(r.get("reward"))) is not None]
    if not rewards and metric_rows:
        latest = max(metric_rows, key=lambda r: r.get("ts") or "")
        lrew = lr._f(latest.get("lr"))
        rewards = [lrew] if lrew is not None else []
    deals = sum(1 for r in eps if str(r.get("deal")).lower() == "true")
    buckets = sorted({r.get("bucket") for r in rows if r.get("bucket")})
    ts = job.get("ts") or min((r.get("ts") for r in rows if r.get("ts")), default=None)
    return {
        "run_id": rid,
        "ts": ts,
        "updated_ts": lr._latest_ts(rows, ts),
        "category": job.get("jt") or any_row.get("jt") or "other",
        "source": job.get("src") or any_row.get("src"),
        "title": job.get("title") or job.get("jt") or any_row.get("jt") or "run",
        "checkpoint": job.get("ckpt") or any_row.get("ckpt"),
        "episodes": len(eps),
        "deals": deals,
        "mean_reward": round(sum(rewards) / len(rewards), 3) if rewards else None,
        "viol": sum(lr._i(r.get("viol")) or 0 for r in score_rows),
        "buckets": buckets,
        "generations": len(metric_rows),
    }


async def main() -> None:
    if not lr.configured():
        print("No LOGFIRE token configured (set LOGFIRE_TOKEN or LOGFIRE_READ_TOKEN). Nothing to backfill.")
        return
    print(f"Backfilling history from Logfire ({lr._base()}) → {type(get_history()).__name__} …")
    async with httpx.AsyncClient(timeout=60) as client:
        rows = await _bulk_rows(client)

    by_run: dict[str, list[dict]] = {}
    for r in rows:
        rid = r.get("rid")
        if rid and rid not in _SKIP_RUN_IDS:
            by_run.setdefault(rid, []).append(r)

    pairs, summaries, with_moves, human = [], [], 0, 0
    for rid, rrows in by_run.items():
        detail = lr.reconstruct_detail(rid, rrows)
        summary = _summarize(rid, rrows)
        # carry the meta the durable store needs onto the detail (so it can recompute summaries)
        detail.update({k: summary[k] for k in ("ts", "category", "source", "checkpoint")})
        pairs.append((summary, detail))
        summaries.append(summary)
        if detail.get("moves"):
            with_moves += 1
        if (summary["source"] or "") == "human":
            human += 1

    store = get_history()
    store.bulk_replace(pairs)

    print(f"\nDone. {len(summaries)} runs written to {type(store).__name__} "
          f"({human} human-vs-agent), {with_moves} with move-by-move transcripts.")
    cats: dict[str, int] = {}
    for s in summaries:
        cats[s["category"]] = cats.get(s["category"], 0) + 1
    print("  by category: " + ", ".join(f"{k}={v}" for k, v in sorted(cats.items())))


if __name__ == "__main__":
    asyncio.run(main())
