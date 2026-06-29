"""Local, durable history for the human-facing seats (typed `/chat` + voice).

History browsing reads from Logfire (`logfire_read.py`), but Logfire ages records out (retention)
and the read API is rate-limited — so older human chats *disappear* and live ones flicker. Worse,
the live seats never emitted the structured `kind=move` records the transcript view renders, so even
present runs showed no transcript. This module is the fix: an append-only JSONL store, one file per
run under `runs/chat/`, that the seats write move-by-move and outcome-at-close. It is the SAME
process-independent file bus used for training (`gambit/trace.py`), so the web server and the
separate voice worker both append to it and the reader merges it ahead of Logfire.

`list_runs()` / `run_detail()` return the EXACT shapes `logfire_read.fetch_runs` / `fetch_run_detail`
produce, so the reader can splice local runs into its responses with no client change.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

CHAT_RUNS = Path("runs/chat")


def _safe(run_id: str) -> str:
    """Filesystem-safe run id (the threadId / room name the seat groups by)."""
    return "".join(c if (c.isalnum() or c in "-_") else "-" for c in (run_id or ""))[:128]


def _path(run_id: str) -> Path:
    return CHAT_RUNS / f"{_safe(run_id)}.jsonl"


def _now_iso() -> str:
    """UTC ISO-8601, matching Logfire's `start_timestamp` so the UI sorts mixed sources correctly."""
    t = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int((t % 1) * 1e6):06d}+00:00"


def _append(run_id: str, event: dict) -> None:
    if not run_id:
        return
    try:
        CHAT_RUNS.mkdir(parents=True, exist_ok=True)
        with _path(run_id).open("a", buffering=1) as f:
            f.write(json.dumps({"ts": _now_iso(), **event}) + "\n")
    except Exception:  # noqa: BLE001 — persistence must never break a live conversation
        pass


# --- writers (called by the seats) -----------------------------------------------------------

def ensure_job(run_id: str, *, source: str = "human", title: str | None = None,
               checkpoint: str | None = None, category: str = "human-vs-agent") -> None:
    """Write the run's root `job` record once (first turn). Idempotent: skipped if the file exists."""
    if not run_id or _path(run_id).exists():
        return
    _append(run_id, {"kind": "job", "source": source, "category": category,
                     "title": title or "chat", "checkpoint": checkpoint})


def record_move(run_id: str, *, role: str, action: str | None,
                offer: float | None = None, text: str = "") -> None:
    _append(run_id, {"kind": "move", "role": role, "action": action, "offer": offer, "text": text})


def record_outcome(run_id: str, *, deal: bool, price: float | None = None,
                   surplus: float | None = None, reward: float | None = None,
                   turns: int | None = None, bucket: str | None = None,
                   result: str | None = None) -> None:
    _append(run_id, {"kind": "outcome", "deal": deal, "price": price, "surplus": surplus,
                     "reward": reward if reward is not None else surplus, "turns": turns,
                     "bucket": bucket, "result": result})


# --- readers (called by logfire_read to merge ahead of Logfire) -------------------------------

def has(run_id: str) -> bool:
    return bool(run_id) and _path(run_id).exists()


def has_outcome(run_id: str) -> bool:
    """Whether a terminal outcome was already recorded — so a closed chat isn't double-counted if the
    buyer keeps typing after the deal/walk."""
    p = _path(run_id)
    return p.exists() and any(r.get("kind") == "outcome" for r in _read(p))


def _read(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except Exception:  # noqa: BLE001
        return []
    return out


def _detail_from_rows(run_id: str, rows: list[dict]) -> dict:
    """Reconstruct one run's detail in `logfire_read.fetch_run_detail`'s shape."""
    moves, outcomes, title, checkpoint = [], [], None, None
    for r in rows:
        k = r.get("kind")
        if k == "move":
            moves.append({"role": (r.get("role") or "seller").lower(), "action": r.get("action"),
                          "offer": r.get("offer"), "text": r.get("text") or ""})
        elif k == "outcome":
            outcomes.append({"result": r.get("result"), "deal": bool(r.get("deal")),
                             "price": r.get("price"), "reward": r.get("reward"),
                             "surplus": r.get("surplus"), "skill": None, "viol": 0,
                             "turns": r.get("turns"), "bucket": r.get("bucket"), "gen": None})
        elif k == "job":
            title = r.get("title") or title
            checkpoint = r.get("checkpoint") or checkpoint
    updated = rows[-1].get("ts") if rows else None
    return {"run_id": run_id, "title": title, "checkpoint": checkpoint, "updated_ts": updated,
            "moves": moves, "outcomes": outcomes, "reflections": [], "curve": [],
            "samples": [], "events": [], "generations": 0, "spans": len(rows)}


def run_detail(run_id: str) -> dict | None:
    """Full local detail for one run, or None if we have no local file for it."""
    p = _path(run_id)
    if not p.exists():
        return None
    return _detail_from_rows(run_id, _read(p))


def list_runs() -> list[dict]:
    """One summary row per local run, in `logfire_read.fetch_runs`'s shape (newest first)."""
    if not CHAT_RUNS.exists():
        return []
    runs: list[dict] = []
    for p in CHAT_RUNS.glob("*.jsonl"):
        rows = _read(p)
        if not rows:
            continue
        job = next((r for r in rows if r.get("kind") == "job"), {})
        outs = [r for r in rows if r.get("kind") == "outcome"]
        rewards = [r["reward"] for r in outs if isinstance(r.get("reward"), (int, float))]
        deals = sum(1 for r in outs if r.get("deal"))
        buckets = sorted({r.get("bucket") for r in outs if r.get("bucket")})
        runs.append({
            "run_id": p.stem,
            "ts": rows[0].get("ts"),
            "updated_ts": rows[-1].get("ts"),
            "category": job.get("category") or "human-vs-agent",
            "source": job.get("source") or "human",
            "title": job.get("title") or "chat",
            "checkpoint": job.get("checkpoint"),
            "episodes": len(outs),
            "deals": deals,
            "mean_reward": round(sum(rewards) / len(rewards), 3) if rewards else None,
            "viol": 0,
            "buckets": buckets,
            "generations": 0,
        })
    runs.sort(key=lambda r: r.get("updated_ts") or "", reverse=True)
    return runs


def signature() -> tuple[int, str]:
    """Cheap change-token (run count + newest mtime) so the SSE stream can detect new local runs
    written by another process (the voice worker) without re-reading every file each tick."""
    if not CHAT_RUNS.exists():
        return (0, "")
    files = list(CHAT_RUNS.glob("*.jsonl"))
    newest = max((f.stat().st_mtime for f in files), default=0.0)
    return (len(files), f"{newest:.3f}")
