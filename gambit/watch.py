"""Live RL-run tracing — connect the REAL training loop to the browser.

A training run (`scripts/run_offline.py`) emits events to a per-run JSONL bus (`gambit/trace.py`)
as the genuine engine loop (`engine/improve.py`, via its `on_event` hook) learns. This module:

  * `make_emitter(...)`  — the trainer's hook: writes each generation panel + a couple of
    spotlight negotiations (run move-by-move under the *current* policy) to the run's JSONL.
  * `watch_stream`       — the SSE endpoint: tails a run's JSONL and streams it to the page
    (replays a finished run, follows a live one). It does NOT run its own loop — it watches.
  * `watch_start`        — POST: launch a real training run as a subprocess and return its id.

So the curve, the live negotiations, and the held-out transfer the page shows are the actual
training process, not a demo re-enactment. Deterministic + offline: no API key, no labels.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from gambit import trace
from gambit.negotiation import NegotiationDomain, PolicyStore, situation_key
from gambit.negotiation.domain import run_episode
from gambit.negotiation.policies import KnobSellerPolicy

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SPOTLIGHT_SEEDS = 2          # negotiations streamed move-by-move per generation


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _move(m) -> dict:
    return {"role": m.role, "action": m.action, "offer": m.offer, "text": m.text}


def _outcome(o) -> dict:
    return {"deal": o.deal, "price": o.price, "turns": o.turns, "reason": o.reason,
            "surplus": round(o.surplus, 3), "skill": round(o.skill, 3), "walked_by": o.walked_by}


def _spotlight(domain: NegotiationDomain, policy: PolicyStore, counterparty, seed: int) -> dict:
    """Run ONE negotiation with the current policy and capture its full move-by-move transcript."""
    item = domain.scenario(seed)
    seller = KnobSellerPolicy(policy.knobs, max_turns=domain.max_turns)
    ep = run_episode(item, seller, counterparty, domain.max_turns)
    return {
        "seed": seed, "item": item.name, "list_price": item.list_price, "floor_price": item.floor_price,
        "persona": counterparty.persona.name, "bucket": situation_key(item),
        "moves": [_move(m) for m in ep.moves], "outcome": _outcome(ep.outcome),
    }


def make_emitter(tracer: "trace.Tracer", domain: NegotiationDomain, counterparties, seeds,
                 spotlight_seeds: int = _SPOTLIGHT_SEEDS):
    """The `on_event(gen, policy, panel)` hook passed to `engine.improve`. Writes the generation
    panel (the curve point) and a few spotlight negotiations (the agents interacting) per gen."""
    try:
        pace_seconds = max(0.0, float(os.environ.get("GAMBIT_WATCH_PACE_SECONDS", "0") or "0"))
    except ValueError:
        pace_seconds = 0.0

    def on_event(gen: int, policy, panel: dict) -> None:
        tracer.emit({"type": "gen", "gen": gen, "improved": gen > 0, **panel})
        for seed in list(seeds)[:spotlight_seeds]:
            tracer.emit({"type": "episode", "gen": gen, **_spotlight(domain, policy, counterparties[0], seed)})
        if pace_seconds:
            time.sleep(pace_seconds)

    return on_event


LEAGUE_CURVE = Path("checkpoints/league/curve.jsonl")


def _league_fresh(max_age: float = 900.0) -> bool:
    """Has the league written its per-gen curve within `max_age`? (Gens are slow — minutes — so the
    file is stale BETWEEN gens; use a generous window plus the process check below.)"""
    try:
        return LEAGUE_CURVE.exists() and (time.time() - LEAGUE_CURVE.stat().st_mtime) < max_age
    except Exception:  # noqa: BLE001
        return False


def _league_alive() -> bool:
    """Is a run_league process actually running? The reliable liveness signal between slow gens."""
    try:
        return subprocess.run(["pgrep", "-f", "run_league.py"], capture_output=True).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def _league_live() -> bool:
    """Stream the league when its process is up (covers multi-minute inter-gen gaps) or it just wrote."""
    return LEAGUE_CURVE.exists() and (_league_alive() or _league_fresh())


async def _stream_league(request: Request):
    """Stream the LIVE LLM league's climb straight from its local curve.jsonl (no Logfire rate
    limit): one bus `gen` frame per generation (held-out reward/skill/viol + promotion), then a
    synthesized transfer + done once the run stops. This is the demo's live hero on /live."""
    yield _sse({"type": "start", "train_family": "HeuristicBuyer", "locked_family": "FirmAnchorBuyer", "source": "league"})
    yield _sse({"type": "run", "run_id": "league-main"})
    pos, first, last, sent, idle = 0, None, None, 0, 0
    while True:
        if await request.is_disconnected():
            return
        rows, pos = trace.read_new(LEAGUE_CURVE, pos)
        for e in rows:
            yield _sse({"type": "gen", "gen": e.get("gen"), "reward": e.get("locked_reward"),
                        "skill": e.get("locked_skill"), "viol": e.get("locked_viol", 0),
                        "improved": bool(e.get("promoted")), "n": e.get("locked_n")})
            if first is None:
                first = e
            last, sent = e, sent + 1
        if rows:
            idle = 0
        else:
            idle += 1
            if sent and idle >= 8 and not _league_alive() and not _league_fresh(120):  # league finished
                if first is not None and last is not None and first is not last:
                    yield _sse({"type": "transfer",
                                "locked_start": {"reward": first.get("locked_reward"), "skill": first.get("locked_skill"), "viol": first.get("locked_viol", 0)},
                                "locked_final": {"reward": last.get("locked_reward"), "skill": last.get("locked_skill"), "viol": last.get("locked_viol", 0)},
                                "locked_delta": round((last.get("locked_reward") or 0) - (first.get("locked_reward") or 0), 4)})
                yield _sse({"type": "done"})
                return
            if idle % 12 == 0:
                yield ": keepalive\n\n"
        await asyncio.sleep(1.5)


async def watch_stream(request: Request) -> StreamingResponse:
    """Tail a run and stream it. LIVE PRIORITY: if the LLM league is actively running, stream that
    real climb from its local checkpoint; else `?run=<id>` watches a bus run, otherwise the latest."""
    requested = request.query_params.get("run")

    async def stream():
        # the running LLM league wins — stream its live climb (curve.jsonl, no Logfire rate limit)
        if requested is None and _league_live():
            async for chunk in _stream_league(request):
                yield chunk
            return
        run_id = requested or trace.latest_run()
        announced = False
        while True:
            while run_id is None:                      # no run yet — wait for one to start
                if await request.is_disconnected():
                    return
                if not announced:
                    yield _sse({"type": "waiting"})
                    announced = True
                await asyncio.sleep(0.5)
                run_id = trace.latest_run()

            yield _sse({"type": "run", "run_id": run_id})
            path = trace.RUNS / f"{run_id}.jsonl"
            pos, done, idle = 0, False, 0
            while not done:
                if await request.is_disconnected():
                    return
                events, pos = trace.read_new(path, pos)
                if events:
                    idle = 0
                    for ev in events:
                        yield _sse(ev)
                        if ev.get("type") == "done":
                            done = True
                else:
                    idle += 1
                    if idle % 20 == 0:                 # keepalive comment so proxies don't drop us
                        yield ": keepalive\n\n"
                    await asyncio.sleep(0.25)

            if requested:
                return

            previous = run_id
            run_id, idle = None, 0
            while run_id is None:
                if await request.is_disconnected():
                    return
                latest = trace.latest_run()
                if latest and latest != previous:
                    run_id = latest
                    break
                idle += 1
                if idle % 20 == 0:
                    yield ": keepalive\n\n"
                await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                      "Connection": "keep-alive"})


async def watch_start(request: Request) -> JSONResponse:
    """Launch a REAL training run as a detached subprocess (it emits to runs/<id>.jsonl), and
    return its id so the page can tail it. This is the 'Run training' button."""
    run_id = f"run-{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}"
    env = {**os.environ, "GAMBIT_RUN_ID": run_id, "OFFLINE": "1",
           "GAMBIT_WATCH_PACE_SECONDS": os.environ.get("GAMBIT_WATCH_PACE_SECONDS", "0.45")}
    subprocess.Popen(
        [sys.executable, "scripts/run_offline.py"],
        cwd=str(_REPO_ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return JSONResponse({"run_id": run_id})
