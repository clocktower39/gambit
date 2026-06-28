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
            "coalesce(attributes->>'gambit.reward', attributes->>'locked_reward') reward, "
            "attributes->>'gambit.skill' skill, "
            "coalesce(attributes->>'gambit.viol', attributes->>'locked_viol') viol, "
            "attributes->>'gambit.bucket' bucket "
            # league_gen carries the per-generation locked reward — count it so league runs aren't blank
            "from records where attributes->>'gambit.kind' in ('outcome', 'human_episode', 'league_gen') "
            f"and attributes->>'gambit.run_id' in {_in_clause(list(seen))} limit 8000"
        ))
        for o in outs:
            by_run.setdefault(o["rid"], []).append(o)

    runs = []
    for m in meta:
        rid = m["rid"]
        eps = by_run.get(rid, [])
        rewards = [v for o in eps if (v := _f(o.get("reward"))) is not None]
        deals = sum(1 for o in eps if str(o.get("deal")).lower() == "true")
        buckets = sorted({o.get("bucket") for o in eps if o.get("bucket")})
        runs.append({
            "run_id": rid,
            "ts": m.get("ts"),
            "category": m.get("jt") or "other",
            "source": m.get("src"),
            "title": m.get("title") or m.get("jt") or "run",
            "checkpoint": m.get("ckpt"),
            "episodes": len(eps),
            "deals": deals,
            "mean_reward": round(sum(rewards) / len(rewards), 3) if rewards else None,
            "viol": sum(_i(o.get("viol")) or 0 for o in eps),
            "buckets": buckets,
        })
    return runs


async def fetch_run_detail(client: httpx.AsyncClient, run_id: str) -> dict:
    """Reconstruct ONE run from a single query over all its records (by gambit.run_id): the moves
    (read directly from gambit.role/action/offer/text), per-episode outcomes, the Gemini lessons,
    and a reward-by-generation curve."""
    rid = run_id if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", run_id or "") else ""
    empty = {"run_id": run_id, "title": None, "moves": [], "outcomes": [], "reflections": [], "curve": [], "spans": 0}
    if not rid:
        return empty
    # Filter to the kinds we render — EXCLUDES the thousands of `chat MiniMax-M3` / `agent run`
    # model spans that inherit the run_id via baggage (else a long run's first 2.5k rows are all
    # model calls and we'd never reach the data). `obs.emit()` ships some attrs un-namespaced, so
    # coalesce gambit.X with the bare X for the league's league_gen / sample_episode fields.
    kinds = ("'job','move','outcome','human_episode','reflection','league_gen','generation',"
             "'sample_episode','promotion','rejection','integrity','escalate'")
    rows = await gated(client, (
        "select attributes->>'gambit.kind' kind, attributes->>'gambit.role' role, "
        "attributes->>'gambit.action' action, attributes->>'gambit.offer' offer, attributes->>'gambit.text' text, "
        "attributes->>'gambit.result' result, attributes->>'gambit.deal' deal, attributes->>'gambit.price' price, "
        "attributes->>'gambit.reward' reward, attributes->>'gambit.surplus' surplus, attributes->>'gambit.skill' skill, "
        "attributes->>'gambit.viol' viol, attributes->>'gambit.turns' turns, attributes->>'gambit.bucket' bucket, "
        "attributes->>'gambit.generation' gen, attributes->>'gambit.seller_lesson' sl, "
        "attributes->>'gambit.buyer_lesson' bl, attributes->>'gambit.title' title, "
        "coalesce(attributes->>'gambit.locked_reward', attributes->>'locked_reward') lr, "
        "coalesce(attributes->>'gambit.locked_skill', attributes->>'locked_skill') ls, "
        "coalesce(attributes->>'gambit.locked_viol', attributes->>'locked_viol') lv, "
        "coalesce(attributes->>'gambit.promoted', attributes->>'promoted') promoted, "
        "coalesce(attributes->>'gambit.transcript', attributes->>'transcript') transcript, "
        "coalesce(attributes->>'gambit.verdict', attributes->>'verdict') verdict, "
        "coalesce(attributes->>'gambit.delta', attributes->>'delta') delta, message, start_timestamp ts "
        f"from records where attributes->>'gambit.run_id' = '{rid}' "
        f"and attributes->>'gambit.kind' in ({kinds}) order by start_timestamp asc limit 6000"
    ))
    moves, outcomes, reflections, samples, events, gpts, title = [], [], [], [], [], {}, None
    for r in rows:
        k = r.get("kind")
        if k == "move":
            moves.append({"role": (r.get("role") or "seller").lower(), "action": r.get("action"),
                          "offer": _f(r.get("offer")), "text": r.get("text") or ""})
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
    return {"run_id": run_id, "title": title, "moves": moves, "outcomes": outcomes,
            "reflections": reflections, "curve": curve, "samples": samples, "events": events,
            "generations": len(gpts), "spans": len(rows)}


# --- background list poller (one shared task) ------------------------------------------------

async def _poll_runs() -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            try:
                runs = await fetch_runs(client)
                _runs.clear()
                _runs.extend(runs)
                _runs_ver[0] += 1
            except Exception:  # noqa: BLE001 — keep the poller alive through throttles
                pass
            await asyncio.sleep(60)


def _ensure_poller() -> None:
    if not _poller_started[0] and configured():
        _poller_started[0] = True
        asyncio.create_task(_poll_runs())          # always called from within a running handler


# --- endpoints -------------------------------------------------------------------------------

async def runs_list(request: Request) -> JSONResponse:
    _ensure_poller()
    return JSONResponse({"configured": configured(), "version": _runs_ver[0], "runs": _runs})


_DETAIL_TTL = 30.0          # seconds — short so a LIVE run's detail (growing curve/lessons) refreshes


async def run_detail(request: Request) -> JSONResponse:
    rid = request.query_params.get("run_id", "")
    if not rid:
        return JSONResponse({"error": "run_id required"}, status_code=400)
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
    return JSONResponse(detail)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


async def runs_stream(request: Request) -> StreamingResponse:
    async def gen():
        _ensure_poller()
        last = -1
        while True:
            if await request.is_disconnected():
                return
            if _runs_ver[0] != last:
                last = _runs_ver[0]
                yield _sse({"type": "runs", "configured": configured(), "runs": _runs})
            else:
                yield ": keepalive\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                      "Connection": "keep-alive"})
