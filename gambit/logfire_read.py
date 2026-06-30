"""Comprehensive, categorized history of every run — read from Logfire (canonical attribute schema).

The trace is emitted by `gambit/observability.py` with a canonical, attribute-based contract
(NOT span-name templates):

  * Every record carries `gambit.kind` ∈ {job, outcome, move, reflection, generation, episode}
    and — via baggage — `gambit.run_id / job_type / source / checkpoint / generation`.
  * A **run** = all records sharing `gambit.run_id` (a browser chat is many traces, one run_id).
  * `kind=job` (root): job_type, source, run_id, checkpoint, title, generation.
  * `kind=outcome`: deal, result, price, reward, surplus, skill, viol, turns, bucket, generation.
  * `kind=move`: role, action, offer, text, reasoning  (read directly — no transcript regex).
  * `kind=reflection`: bucket, seller_lesson, buyer_lesson, surplus, viol.

So: category = `gambit.job_type`, human/agent split = `gambit.source`, title = `gambit.title`,
the curve = `gambit.generation` × `gambit.reward` over outcomes. We group by `run_id`, never join
to the root span (baggage already stamps run_id onto every child record).

Logfire's read API is rate-limited per minute per org, so query volume is tiny and constant: one
shared poller refreshes a cached run list slowly; per-run detail is one query, cached; every query
passes a serialized rate gate honoring Retry-After.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from gambit.settings import settings
from gambit import history


# --- connection ------------------------------------------------------------------------------

def _token() -> str:
    return os.environ.get("LOGFIRE_READ_TOKEN") or settings.logfire_token or ""


def _base() -> str:
    return "https://logfire-eu.pydantic.dev" if "_eu_" in _token()[:14] else "https://logfire-us.pydantic.dev"


def configured() -> bool:
    return bool(_token())


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _i(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def _latest_ts(rows: list[dict], fallback: str | None = None) -> str | None:
    vals = [r.get("ts") for r in rows if r.get("ts")]
    if fallback:
        vals.append(fallback)
    return max(vals) if vals else fallback


def _in_clause(ids: list[str]) -> str:
    safe = [i for i in ids if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", i or "")]
    return "(" + ",".join("'" + i + "'" for i in safe) + ")" if safe else "('')"


# --- serialized, rate-limited query gate -----------------------------------------------------

_MIN_INTERVAL = 7.0
_gate = asyncio.Lock()
_last = [0.0]


async def _raw(client: httpx.AsyncClient, sql: str) -> list[dict]:
    r = await client.get(f"{_base()}/v1/query", params={"sql": sql},
                         headers={"Authorization": f"Bearer {_token()}", "Accept": "application/json"})
    r.raise_for_status()
    payload = r.json()
    cols = payload.get("columns", [])
    names = [c["name"] for c in cols]
    vals = [c["values"] for c in cols]
    n = len(vals[0]) if vals else 0
    return [{names[j]: vals[j][i] for j in range(len(names))} for i in range(n)]


async def gated(client: httpx.AsyncClient, sql: str, *, retries: int = 2) -> list[dict]:
    """Serialize + space every query; retry on 429 honoring Retry-After."""
    for attempt in range(retries + 1):
        async with _gate:
            wait = _MIN_INTERVAL - (time.monotonic() - _last[0])
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                rows = await _raw(client, sql)
                _last[0] = time.monotonic()
                return rows
            except httpx.HTTPStatusError as e:
                _last[0] = time.monotonic()
                if e.response is not None and e.response.status_code == 429 and attempt < retries:
                    try:
                        ra = int(e.response.headers.get("retry-after", "12"))
                    except Exception:  # noqa: BLE001
                        ra = 12
                    await asyncio.sleep(max(ra, 5) + 1)
                    continue
                raise
    return []


# --- run list (cached snapshot) --------------------------------------------------------------

_runs: list[dict] = []
_runs_ver = [0]
_details: dict[str, tuple[float, dict]] = {}    # run_id -> (cached_at_monotonic, detail), TTL'd
_poller_started = [False]


async def fetch_runs(client: httpx.AsyncClient, limit: int = 300) -> list[dict]:
    """One row per run (grouped by gambit.run_id). Two queries: job roots, then outcomes scoped to
    those run_ids — grouped by run_id (baggage stamps run_id on every outcome, no join needed)."""
    jobs = await gated(client, (
        "select attributes->>'gambit.run_id' rid, attributes->>'gambit.job_type' jt, "
        "attributes->>'gambit.source' src, attributes->>'gambit.title' title, "
        "attributes->>'gambit.checkpoint' ckpt, start_timestamp ts "
        "from records where attributes->>'gambit.kind' = 'job' "
        f"order by start_timestamp desc limit {int(limit)}"
    ))
    meta: list[dict] = []
    seen: set[str] = set()
    for j in jobs:                       # newest job record per run_id wins
        rid = j.get("rid")
        if rid and rid not in seen:
            seen.add(rid)
            meta.append(j)

    by_run: dict[str, list[dict]] = {}
    if seen:
        outs = await gated(client, (
            "select attributes->>'gambit.run_id' rid, attributes->>'gambit.deal' deal, "
            "attributes->>'gambit.kind' kind, "
            "coalesce(attributes->>'gambit.reward', attributes->>'reward', "
            "attributes->>'gambit.locked_reward', attributes->>'locked_reward') reward, "
            "coalesce(attributes->>'gambit.skill', attributes->>'skill', "
            "attributes->>'gambit.locked_skill', attributes->>'locked_skill') skill, "
            "coalesce(attributes->>'gambit.viol', attributes->>'viol', "
            "attributes->>'gambit.locked_viol', attributes->>'locked_viol') viol, "
            "coalesce(attributes->>'gambit.bucket', attributes->>'bucket') bucket, "
            "coalesce(attributes->>'gambit.generation', attributes->>'generation') gen, "
            "start_timestamp ts "
            "from records where attributes->>'gambit.kind' in "
            "('outcome', 'human_episode', 'league_gen', 'reflection', 'sample_episode', "
            "'promotion', 'rejection', 'integrity', 'escalate') "
            f"and attributes->>'gambit.run_id' in {_in_clause(list(seen))} "
            "order by start_timestamp asc limit 8000"
        ))
        for o in outs:
            by_run.setdefault(o["rid"], []).append(o)

    runs = []
    for m in meta:
        rid = m["rid"]
        rows = by_run.get(rid, [])
        eps = [o for o in rows if o.get("kind") in ("outcome", "human_episode")]
        metric_rows = [o for o in rows if o.get("kind") == "league_gen"]
        score_rows = eps if eps else metric_rows
        rewards = [v for o in eps if (v := _f(o.get("reward"))) is not None]
        if not rewards and metric_rows:
            latest_metric = max(metric_rows, key=lambda o: o.get("ts") or "")
            latest_reward = _f(latest_metric.get("reward"))
            rewards = [latest_reward] if latest_reward is not None else []
        deals = sum(1 for o in eps if str(o.get("deal")).lower() == "true")
        buckets = sorted({o.get("bucket") for o in rows if o.get("bucket")})
        runs.append({
            "run_id": rid,
            "ts": m.get("ts"),
            "updated_ts": _latest_ts(rows, m.get("ts")),
            "category": m.get("jt") or "other",
            "source": m.get("src"),
            "title": m.get("title") or m.get("jt") or "run",
            "checkpoint": m.get("ckpt"),
            "episodes": len(eps),
            "deals": deals,
            "mean_reward": round(sum(rewards) / len(rewards), 3) if rewards else None,
            "viol": sum(_i(o.get("viol")) or 0 for o in score_rows),
            "buckets": buckets,
            "generations": len(metric_rows),
        })
    return runs


# The renderable kinds — EXCLUDES the thousands of `chat MiniMax-M3` / `agent run` model spans that
# inherit the run_id via baggage (else a long run's first 2.5k rows are all model calls and we'd never
# reach the data). `obs.emit()` ships some attrs un-namespaced, so the SELECT coalesces gambit.X with
# the bare X for the league's league_gen / sample_episode fields.
_DETAIL_KINDS = ("'job','move','outcome','human_episode','reflection','league_gen','generation',"
                 "'sample_episode','promotion','rejection','integrity','escalate'")

# The column projection shared by the single-run detail query and the bulk backfill — kept in one
# place so the two paths reconstruct from byte-identical row shapes.
_DETAIL_SELECT = (
    "attributes->>'gambit.kind' kind, coalesce(attributes->>'gambit.role', attributes->>'role') role, "
    "coalesce(attributes->>'gambit.action', attributes->>'action') action, "
    "coalesce(attributes->>'gambit.offer', attributes->>'offer') offer, "
    "coalesce(attributes->>'gambit.text', attributes->>'text') text, "
    "coalesce(attributes->>'gambit.result', attributes->>'result') result, "
    "coalesce(attributes->>'gambit.deal', attributes->>'deal') deal, "
    "coalesce(attributes->>'gambit.price', attributes->>'price') price, "
    "coalesce(attributes->>'gambit.reward', attributes->>'reward') reward, "
    "coalesce(attributes->>'gambit.surplus', attributes->>'surplus') surplus, "
    "coalesce(attributes->>'gambit.skill', attributes->>'skill') skill, "
    "coalesce(attributes->>'gambit.viol', attributes->>'viol') viol, "
    "coalesce(attributes->>'gambit.turns', attributes->>'turns') turns, "
    "coalesce(attributes->>'gambit.bucket', attributes->>'bucket') bucket, "
    "coalesce(attributes->>'gambit.generation', attributes->>'generation') gen, "
    "coalesce(attributes->>'gambit.seller_lesson', attributes->>'seller_lesson') sl, "
    "coalesce(attributes->>'gambit.buyer_lesson', attributes->>'buyer_lesson') bl, "
    "coalesce(attributes->>'gambit.title', attributes->>'title') title, "
    "coalesce(attributes->>'gambit.job_type', attributes->>'job_type') jt, "
    "coalesce(attributes->>'gambit.source', attributes->>'source') src, "
    "coalesce(attributes->>'gambit.checkpoint', attributes->>'checkpoint') ckpt, "
    "coalesce(attributes->>'gambit.locked_reward', attributes->>'locked_reward') lr, "
    "coalesce(attributes->>'gambit.locked_skill', attributes->>'locked_skill') ls, "
    "coalesce(attributes->>'gambit.locked_viol', attributes->>'locked_viol') lv, "
    "coalesce(attributes->>'gambit.promoted', attributes->>'promoted') promoted, "
    "coalesce(attributes->>'gambit.transcript', attributes->>'transcript') transcript, "
    "coalesce(attributes->>'gambit.verdict', attributes->>'verdict') verdict, "
    "coalesce(attributes->>'gambit.delta', attributes->>'delta') delta, message, "
    "attributes->>'gambit.run_id' rid, start_timestamp ts"
)


def reconstruct_detail(run_id: str, rows: list[dict]) -> dict:
    """Build one run's detail dict from its already-fetched records. Shared by the live single-run
    query and the bulk historical backfill so both produce the same shape."""
    moves, outcomes, reflections, samples, events, gpts, title = [], [], [], [], [], {}, None
    for r in rows:
        k = r.get("kind")
        if k == "move":
            moves.append({"role": (r.get("role") or "seller").lower(), "action": r.get("action"),
                          "offer": _f(r.get("offer")), "text": r.get("text") or "",
                          "ts": r.get("ts") or r.get("start_timestamp")})
        elif k in ("outcome", "human_episode"):
            outcomes.append({
                "result": r.get("result"), "deal": str(r.get("deal")).lower() == "true",
                "price": _f(r.get("price")), "reward": _f(r.get("reward")), "surplus": _f(r.get("surplus")),
                "skill": _f(r.get("skill")), "viol": _i(r.get("viol")) or 0, "turns": _i(r.get("turns")),
                "bucket": r.get("bucket"), "gen": _i(r.get("gen")),
            })
        elif k == "league_gen":                      # the league's per-generation curve point
            g = _i(r.get("gen"))
            if g is not None:
                gpts[g] = {"gen": g, "reward": _f(r.get("lr")), "skill": _f(r.get("ls")),
                           "viol": _i(r.get("lv")) or 0, "promoted": str(r.get("promoted")).lower() == "true"}
        elif k == "sample_episode":                  # the league's representative transcripts
            if r.get("transcript"):
                samples.append({"bucket": r.get("bucket"), "reward": _f(r.get("reward")),
                                "skill": _f(r.get("skill")), "transcript": r.get("transcript")})
        elif k == "reflection":
            if r.get("sl") or r.get("bl"):
                reflections.append({"bucket": r.get("bucket"), "seller_lesson": r.get("sl"),
                                    "buyer_lesson": r.get("bl"), "surplus": _f(r.get("surplus")),
                                    "viol": _i(r.get("viol")) or 0})
        elif k in ("promotion", "rejection", "integrity", "escalate"):
            events.append({"kind": k, "gen": _i(r.get("gen")), "bucket": r.get("bucket"),
                           "verdict": r.get("verdict"), "delta": _f(r.get("delta")), "msg": r.get("message")})
        elif k == "job" and r.get("title"):
            title = r.get("title")

    # the curve: prefer the league's per-gen locked reward; else aggregate outcome rewards by gen
    if gpts:
        curve = [gpts[g] for g in sorted(gpts)]
    else:
        gens: dict[int, list[float]] = {}
        for o in outcomes:
            if o["gen"] is not None and o["reward"] is not None:
                gens.setdefault(o["gen"], []).append(o["reward"])
        curve = [{"gen": g, "reward": round(sum(v) / len(v), 4)} for g, v in sorted(gens.items())]
    return {"run_id": run_id, "title": title, "updated_ts": _latest_ts(rows), "moves": moves, "outcomes": outcomes,
            "reflections": reflections, "curve": curve, "samples": samples, "events": events,
            "generations": len(gpts), "spans": len(rows)}


async def fetch_run_detail(client: httpx.AsyncClient, run_id: str) -> dict:
    """Reconstruct ONE run from a single query over its records (by gambit.run_id)."""
    rid = run_id if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", run_id or "") else ""
    if not rid:
        return {"run_id": run_id, "title": None, "moves": [], "outcomes": [], "reflections": [], "curve": [], "spans": 0}
    rows = await gated(client, (
        f"select {_DETAIL_SELECT} from records where attributes->>'gambit.run_id' = '{rid}' "
        f"and attributes->>'gambit.kind' in ({_DETAIL_KINDS}) order by start_timestamp asc limit 6000"
    ))
    return reconstruct_detail(rid, rows)


# --- background list poller (one shared task) ------------------------------------------------
# Durability lives in `gambit.history` (Postgres on the deploy, files locally) — so the app serves
# history even when cold or throttled. The poller just refreshes Logfire's live view on top and
# snapshots it into the durable store. A one-time `scripts/backfill_history.py` seeds the archive.

async def _poll_runs() -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            try:
                runs = await fetch_runs(client)
                _runs.clear()
                _runs.extend(runs)
                _runs_ver[0] += 1
                history.get_history().save_list_snapshot(runs)   # persist so it survives a restart
            except Exception:  # noqa: BLE001 — keep the poller alive through throttles
                pass
            await asyncio.sleep(150)  # history only; keep well under the org per-min limit


def _ensure_poller() -> None:
    if not _poller_started[0] and configured():
        _poller_started[0] = True
        asyncio.create_task(_poll_runs())           # always called from within a running handler


# --- endpoints -------------------------------------------------------------------------------

def _merge_runs(remote: list[dict], local: list[dict]) -> list[dict]:
    """Splice durable local human-chat runs ahead of Logfire (local wins on run_id collisions, since
    it carries the real transcript/outcome), newest first."""
    by_id = {r["run_id"]: r for r in remote if r.get("run_id")}
    for r in local:                      # local overrides — it has the moves Logfire dropped
        if r.get("run_id"):
            by_id[r["run_id"]] = r
    return sorted(by_id.values(), key=lambda r: r.get("updated_ts") or r.get("ts") or "", reverse=True)


async def runs_list(request: Request) -> JSONResponse:
    _ensure_poller()
    runs = _merge_runs(_runs, history.get_history().list_runs())   # durable store wins; serves cold/throttled
    return JSONResponse({"configured": configured() or bool(runs), "version": _runs_ver[0], "runs": runs})


_DETAIL_TTL = 30.0          # seconds — short so a LIVE run's detail (growing curve/lessons) refreshes


async def run_detail(request: Request) -> JSONResponse:
    rid = request.query_params.get("run_id", "")
    if not rid:
        return JSONResponse({"error": "run_id required"}, status_code=400)
    h = history.get_history()
    local = h.run_detail(rid)                     # durable store wins: transcript + backfilled archive, no rate-limit hit
    if local is not None:
        return JSONResponse(local)
    cached = _details.get(rid)
    if cached and (time.monotonic() - cached[0]) < _DETAIL_TTL:
        return JSONResponse(cached[1])      # fresh enough — a live run still updates within TTL
    if not configured():
        return JSONResponse({"error": "no logfire token"}, status_code=503)
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            detail = await fetch_run_detail(client, rid)
        except httpx.HTTPStatusError as e:
            code = e.response.status_code if e.response is not None else 500
            if cached:
                return JSONResponse(cached[1])   # serve last-good rather than error on a transient throttle
            return JSONResponse({"error": f"logfire {code}", "retry": code == 429}, status_code=code)
        except Exception as e:  # noqa: BLE001
            if cached:
                return JSONResponse(cached[1])
            return JSONResponse({"error": str(e)[:160], "retry": True}, status_code=502)
    if detail.get("moves") or detail.get("outcomes") or detail.get("reflections") or detail.get("curve"):
        _details[rid] = (time.monotonic(), detail)   # (ts, detail) — TTL'd so live runs aren't frozen
        h.save_detail(rid, detail)                   # persist so a restart / throttle still serves it
    return JSONResponse(detail)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def runs_stream(request: Request) -> StreamingResponse:
    async def gen():
        _ensure_poller()
        last, last_local = -1, None
        while True:
            if await request.is_disconnected():
                return
            h = history.get_history()
            local_sig = h.version()              # detects chats written by another process (the voice worker)
            if _runs_ver[0] != last or local_sig != last_local:
                last, last_local = _runs_ver[0], local_sig
                runs = _merge_runs(_runs, h.list_runs())
                yield _sse({"type": "runs", "configured": configured() or bool(runs), "runs": runs})
            else:
                yield ": keepalive\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                      "Connection": "keep-alive"})
