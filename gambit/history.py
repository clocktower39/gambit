"""Durable history for the human seats + backfilled traces — one facade, two backends.

History (chat transcripts, run summaries, the backfilled Logfire archive) must survive process
restarts and the read-API rate limit. This module is the single seam the seats, the reader, and the
backfill all go through:

  * `PostgresHistory` — used when `DATABASE_URL` is set (the Oracle-VM deploy): one `history_runs`
    table, run_id-keyed, holding each run's summary + full detail as JSONB. Truly durable.
  * `FileHistory` — the no-DB default: live chats append to `runs/chat/*.jsonl` (via `runstore`) and
    backfilled/snapshotted runs live under `runs/cache/`. Durable on any persistent disk.

`get_history()` picks Postgres when the DSN is present and psycopg connects, else files — exactly the
`legacy.storage.get_store()` contract, so the app runs before the DB exists. Both backends return the
SAME shapes `logfire_read` produces, so nothing downstream changes.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from gambit import runstore
from gambit.settings import settings


def _now_iso() -> str:
    t = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int((t % 1) * 1e6):06d}+00:00"


def _summarize(run_id: str, detail: dict) -> dict:
    """A run-list row computed from a run's detail dict — the shape `logfire_read.fetch_runs` returns."""
    outs = detail.get("outcomes") or []
    rewards = [o["reward"] for o in outs if isinstance(o.get("reward"), (int, float))]
    deals = sum(1 for o in outs if o.get("deal"))
    buckets = sorted({o.get("bucket") for o in outs if o.get("bucket")})
    curve = detail.get("curve") or []
    return {
        "run_id": run_id,
        "ts": detail.get("ts") or detail.get("updated_ts"),
        "updated_ts": detail.get("updated_ts"),
        "category": detail.get("category") or "human-vs-agent",
        "source": detail.get("source") or "human",
        "title": detail.get("title") or "chat",
        "checkpoint": detail.get("checkpoint"),
        "episodes": len(outs),
        "deals": deals,
        "mean_reward": round(sum(rewards) / len(rewards), 3) if rewards else None,
        "viol": sum(int(o.get("viol") or 0) for o in outs),
        "buckets": buckets,
        "generations": len(curve),
    }


# =================================================================================================
# File backend (default) — live chat via runstore JSONL; backfill/snapshot under runs/cache/.
# =================================================================================================

class FileHistory:
    CACHE_DIR = Path("runs/cache")
    LIST_FILE = CACHE_DIR / "runs.json"
    DETAIL_DIR = CACHE_DIR / "detail"

    # --- live chat (delegates to the per-conversation JSONL store) ---
    def ensure_job(self, run_id, *, source="human", title=None, checkpoint=None, category="human-vs-agent"):
        runstore.ensure_job(run_id, source=source, title=title, checkpoint=checkpoint, category=category)

    def record_move(self, run_id, *, role, action, offer=None, text=""):
        runstore.record_move(run_id, role=role, action=action, offer=offer, text=text)

    def record_outcome(self, run_id, **kw):
        runstore.record_outcome(run_id, **kw)

    def has_outcome(self, run_id) -> bool:
        return runstore.has_outcome(run_id)

    # --- backfill + snapshot (the durable archive under runs/cache/) ---
    @staticmethod
    def _safe(rid: str) -> str:
        return "".join(c if (c.isalnum() or c in "-_") else "-" for c in (rid or ""))[:128]

    def bulk_replace(self, runs: list[tuple[dict, dict]]) -> None:
        """Replace the archive with (summary, detail) pairs — the one-shot historical backfill."""
        try:
            self.DETAIL_DIR.mkdir(parents=True, exist_ok=True)
            for summary, detail in runs:
                (self.DETAIL_DIR / f"{self._safe(summary['run_id'])}.json").write_text(json.dumps(detail))
            summaries = sorted((s for s, _ in runs),
                               key=lambda s: s.get("updated_ts") or s.get("ts") or "", reverse=True)
            self.LIST_FILE.write_text(json.dumps(summaries))
        except Exception:  # noqa: BLE001
            pass

    def save_list_snapshot(self, runs: list[dict]) -> None:
        """Persist the poller's live run-list snapshot so a cold start serves it immediately."""
        try:
            self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self.LIST_FILE.write_text(json.dumps(runs))
        except Exception:  # noqa: BLE001
            pass

    def save_detail(self, run_id: str, detail: dict) -> None:
        try:
            self.DETAIL_DIR.mkdir(parents=True, exist_ok=True)
            (self.DETAIL_DIR / f"{self._safe(run_id)}.json").write_text(json.dumps(detail))
        except Exception:  # noqa: BLE001
            pass

    def _load_list(self) -> list[dict]:
        try:
            if self.LIST_FILE.exists():
                return json.loads(self.LIST_FILE.read_text())
        except Exception:  # noqa: BLE001
            pass
        return []

    def _load_detail(self, run_id: str) -> dict | None:
        try:
            p = self.DETAIL_DIR / f"{self._safe(run_id)}.json"
            if p.exists():
                return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            pass
        return None

    # --- reads ---
    def list_runs(self) -> list[dict]:
        by_id = {r["run_id"]: r for r in self._load_list() if r.get("run_id")}
        for r in runstore.list_runs():           # live chats override the archived copy (they have moves)
            if r.get("run_id"):
                by_id[r["run_id"]] = r
        return sorted(by_id.values(), key=lambda r: r.get("updated_ts") or r.get("ts") or "", reverse=True)

    def run_detail(self, run_id: str) -> dict | None:
        return runstore.run_detail(run_id) or self._load_detail(run_id)

    def version(self) -> tuple:
        """Cheap change-token so the SSE stream re-emits when a new run lands (incl. cross-process)."""
        chat = runstore.signature()
        try:
            mtime = self.LIST_FILE.stat().st_mtime if self.LIST_FILE.exists() else 0.0
        except Exception:  # noqa: BLE001
            mtime = 0.0
        return (chat, f"{mtime:.3f}")


# =================================================================================================
# Postgres backend — used on the deploy (DATABASE_URL set). One run_id-keyed table, JSONB detail.
# =================================================================================================

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history_runs (
    run_id      TEXT PRIMARY KEY,
    source      TEXT,
    category    TEXT,
    title       TEXT,
    checkpoint  TEXT,
    ts          TEXT,
    updated_ts  TEXT,
    summary     JSONB,
    detail      JSONB,
    created_at  TIMESTAMPTZ DEFAULT now()
);
"""


class PostgresHistory:
    """Durable run store on Postgres. Same interface as FileHistory."""

    def __init__(self, dsn: str):
        import psycopg
        self._psycopg = psycopg
        self.conn = psycopg.connect(dsn, autocommit=True)
        with self.conn.cursor() as cur:
            cur.execute(_SCHEMA)

    def _jsonb(self, value):
        from psycopg.types.json import Jsonb
        return Jsonb(value)

    def _get_detail(self, run_id: str) -> dict | None:
        with self.conn.cursor() as cur:
            cur.execute("SELECT detail FROM history_runs WHERE run_id = %s", (run_id,))
            row = cur.fetchone()
        return row[0] if row and row[0] is not None else None

    def _write(self, run_id: str, detail: dict) -> None:
        """Upsert a run from its full detail dict (recomputing the summary). The single write path."""
        summary = _summarize(run_id, detail)
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO history_runs (run_id, source, category, title, checkpoint, ts, updated_ts, summary, detail)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (run_id) DO UPDATE SET source=EXCLUDED.source, category=EXCLUDED.category,"
                " title=EXCLUDED.title, checkpoint=EXCLUDED.checkpoint, ts=COALESCE(history_runs.ts, EXCLUDED.ts),"
                " updated_ts=EXCLUDED.updated_ts, summary=EXCLUDED.summary, detail=EXCLUDED.detail",
                (run_id, summary["source"], summary["category"], summary["title"], summary["checkpoint"],
                 summary["ts"], summary["updated_ts"], self._jsonb(summary), self._jsonb(detail)),
            )

    def _blank_detail(self, run_id, *, source, title, checkpoint, category) -> dict:
        now = _now_iso()
        return {"run_id": run_id, "source": source, "category": category, "title": title,
                "checkpoint": checkpoint, "ts": now, "updated_ts": now, "moves": [], "outcomes": [],
                "reflections": [], "curve": [], "samples": [], "events": [], "generations": 0, "spans": 0}

    # --- live chat (read-modify-write the run's JSONB detail; chat volume is low) ---
    def ensure_job(self, run_id, *, source="human", title=None, checkpoint=None, category="human-vs-agent"):
        if self._get_detail(run_id) is None:
            self._write(run_id, self._blank_detail(run_id, source=source, title=title or "chat",
                                                   checkpoint=checkpoint, category=category))

    def record_move(self, run_id, *, role, action, offer=None, text=""):
        detail = self._get_detail(run_id) or self._blank_detail(run_id, source="human", title="chat",
                                                                checkpoint=None, category="human-vs-agent")
        detail.setdefault("moves", []).append(
            {"role": role, "action": action, "offer": offer, "text": text, "ts": _now_iso()})
        detail["updated_ts"] = _now_iso()
        self._write(run_id, detail)

    def record_outcome(self, run_id, *, deal, price=None, surplus=None, reward=None, turns=None,
                       bucket=None, result=None):
        detail = self._get_detail(run_id) or self._blank_detail(run_id, source="human", title="chat",
                                                                checkpoint=None, category="human-vs-agent")
        detail.setdefault("outcomes", []).append({
            "result": result, "deal": bool(deal), "price": price,
            "reward": reward if reward is not None else surplus, "surplus": surplus,
            "skill": None, "viol": 0, "turns": turns, "bucket": bucket, "gen": None})
        detail["updated_ts"] = _now_iso()
        self._write(run_id, detail)

    def has_outcome(self, run_id) -> bool:
        detail = self._get_detail(run_id)
        return bool(detail and detail.get("outcomes"))

    # --- backfill + snapshot ---
    def bulk_replace(self, runs: list[tuple[dict, dict]]) -> None:
        for _summary, detail in runs:
            self._write(detail.get("run_id") or _summary["run_id"], detail)

    def save_list_snapshot(self, runs: list[dict]) -> None:
        """Upsert summary-only rows for runs the poller saw (detail filled in on first view)."""
        for s in runs:
            rid = s.get("run_id")
            if not rid:
                continue
            with self.conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO history_runs (run_id, source, category, title, checkpoint, ts, updated_ts, summary)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                    " ON CONFLICT (run_id) DO UPDATE SET source=EXCLUDED.source, category=EXCLUDED.category,"
                    " title=EXCLUDED.title, checkpoint=EXCLUDED.checkpoint, updated_ts=EXCLUDED.updated_ts,"
                    " summary=EXCLUDED.summary",
                    (rid, s.get("source"), s.get("category"), s.get("title"), s.get("checkpoint"),
                     s.get("ts"), s.get("updated_ts"), self._jsonb(s)),
                )

    def save_detail(self, run_id: str, detail: dict) -> None:
        self._write(run_id, detail)

    # --- reads ---
    def list_runs(self) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT summary FROM history_runs WHERE summary IS NOT NULL "
                        "ORDER BY updated_ts DESC NULLS LAST")
            return [r[0] for r in cur.fetchall()]

    def run_detail(self, run_id: str) -> dict | None:
        detail = self._get_detail(run_id)
        return detail or None

    def version(self) -> tuple:
        with self.conn.cursor() as cur:
            cur.execute("SELECT count(*), max(updated_ts) FROM history_runs")
            n, mx = cur.fetchone()
        return (int(n or 0), mx or "")


# =================================================================================================

def export_all(store) -> dict[str, dict]:
    """Every run's self-contained detail (meta from the list summary folded in), keyed by run_id.
    Powers the transcript-recovery merge and the file→Postgres migration — works on either backend."""
    out: dict[str, dict] = {}
    for s in store.list_runs():
        rid = s.get("run_id")
        if not rid:
            continue
        d = dict(store.run_detail(rid) or {})
        for k in ("category", "source", "title", "checkpoint", "ts", "updated_ts"):
            d.setdefault(k, s.get(k))
        d["run_id"] = rid
        out[rid] = d
    return out


def summarize(run_id: str, detail: dict) -> dict:
    """Public wrapper so scripts compute list rows the same way both backends do."""
    return _summarize(run_id, detail)


_store = None


def get_history():
    """Postgres when DATABASE_URL is set and connects; else the file store (local dev / no DB yet)."""
    global _store
    if _store is not None:
        return _store
    dsn = settings.database_url
    if dsn:
        try:
            _store = PostgresHistory(dsn)
            return _store
        except Exception as exc:  # noqa: BLE001 — driver missing / DB unreachable
            print(f"[history] Postgres unavailable ({exc}); using file store.")
    _store = FileHistory()
    return _store
