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

    def on_event(gen: int, policy, panel: dict) -> None:
        tracer.emit({"type": "gen", "gen": gen, "improved": gen > 0, **panel})
        for seed in list(seeds)[:spotlight_seeds]:
            tracer.emit({"type": "episode", "gen": gen, **_spotlight(domain, policy, counterparties[0], seed)})

    return on_event


async def watch_stream(request: Request) -> StreamingResponse:
    """Tail a run's JSONL and stream it to the browser. `?run=<id>` watches a specific run;
    otherwise follow the latest (waiting if none has started yet)."""
    requested = request.query_params.get("run")

    async def stream():
        run_id = requested or trace.latest_run()
        announced = False
        while run_id is None:                          # no run yet — wait for one to start
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
                if idle % 20 == 0:                     # keepalive comment so proxies don't drop us
                    yield ": keepalive\n\n"
                await asyncio.sleep(0.25)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                      "Connection": "keep-alive"})


async def watch_start(request: Request) -> JSONResponse:
    """Launch a REAL training run as a detached subprocess (it emits to runs/<id>.jsonl), and
    return its id so the page can tail it. This is the 'Run training' button."""
    run_id = f"run-{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}"
    env = {**os.environ, "GAMBIT_RUN_ID": run_id, "OFFLINE": "1"}
    subprocess.Popen(
        [sys.executable, "scripts/run_offline.py"],
        cwd=str(_REPO_ROOT), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return JSONResponse({"run_id": run_id})
