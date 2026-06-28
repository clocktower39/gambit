"""Shared run-event bus — what makes the live tracer REAL.

A training run (`scripts/run_offline.py`) and the web server are separate processes, so they
talk through an append-only JSONL file, one per run, under `runs/`. The trainer appends events
as it learns; the watch server tails the file and streams new lines to the browser. Decoupled
(no server needed while training), replayable (re-open a run to see the whole thing), and
deterministic-friendly. One JSON event per line: `{"ts", "type", ...}`.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

RUNS = Path("runs")


def _runs_dir() -> Path:
    RUNS.mkdir(exist_ok=True)
    return RUNS


class Tracer:
    """Append-only event writer for one run. `run_id` is stable; `runs/latest` points at it."""

    def __init__(self, run_id: str | None = None):
        d = _runs_dir()
        self.run_id = run_id or time.strftime("run-%Y%m%d-%H%M%S")
        self.path = d / f"{self.run_id}.jsonl"
        self.f = self.path.open("a", buffering=1)      # line-buffered
        (d / "latest").write_text(self.run_id)

    def emit(self, event: dict) -> None:
        self.f.write(json.dumps({"ts": round(time.time(), 3), **event}) + "\n")
        self.f.flush()

    def close(self) -> None:
        try:
            self.f.close()
        except Exception:
            pass


def latest_run() -> str | None:
    p = RUNS / "latest"
    if p.exists():
        rid = p.read_text().strip()
        if rid and (RUNS / f"{rid}.jsonl").exists():
            return rid
    return None


def read_new(path: Path, pos: int) -> tuple[list[dict], int]:
    """Read complete events appended since byte offset `pos`. A partial trailing line (still being
    written) is left for the next poll. Returns (events, new_pos) — byte-accurate for tailing."""
    if not path.exists():
        return [], pos
    with path.open("rb") as f:
        f.seek(pos)
        data = f.read()
    nl = data.rfind(b"\n")
    if nl == -1:                                        # no complete line yet
        return [], pos
    chunk = data[: nl + 1]
    out: list[dict] = []
    for line in chunk.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out, pos + len(chunk)
