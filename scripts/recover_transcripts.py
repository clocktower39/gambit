"""Recover old conversation transcripts from Logfire spans into the durable local store.

The backfill (`backfill_history.py`) restored every run's metadata + curve, but pre-fix conversations
have empty transcripts: the live seats never wrote `kind=move` records. The message TEXT does survive,
though, in spans the normal reader skips — and this script digs it back out, in two tiers:

  * Tier A (clean): the CLI `play.py` sessions logged `seller turn {round}` / `buyer turn {round}
    (human)` / `seller opening` spans carrying `gambit.run_id` + action + offer + text. Grouped by
    run_id → exact transcripts.
  * Tier B (messy): the browser seat's pydantic-ai spans carry no run_id, but `chat MiniMax-M3` holds
    the full `gen_ai.input.messages` history and `agent run` holds the reply (`final_result`), both
    keyed by a stable `gen_ai.conversation.id`. We rebuild each conversation from those, then map it
    back to its run_id by timestamp overlap with the run's `job` spans (best-effort; reported).

Recovered moves are merged into runs that lacked them and written back through `gambit.history`, so the
local store becomes the single source of truth to migrate to Postgres (`scripts/migrate_to_postgres.py`).

    uv run python scripts/recover_transcripts.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `gambit` importable

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from gambit import history, logfire_read as lr  # noqa: E402

_PAGE = 100
_TURN_SPANS = "'seller turn {round}','buyer turn {round} (human)','seller opening'"
_MAP_WINDOW_S = 180.0          # max seconds between a conversation and a run's job span to map them


async def _page(client: httpx.AsyncClient, sql: str) -> list[dict]:
    """One page, riding out the aggressive per-minute org limit with long backoff (one-time job)."""
    for attempt in range(12):
        try:
            return await lr.gated(client, sql)
        except httpx.HTTPStatusError as e:
            if e.response is not None and e.response.status_code == 429:
                wait = 45 + attempt * 10
                print(f"    rate-limited; waiting {wait}s …")
                await asyncio.sleep(wait)
                continue
            raise
    return []


async def _paginate(client: httpx.AsyncClient, select: str, where: str) -> list[dict]:
    rows, cursor = [], ""
    while True:
        w = where + (f" and start_timestamp > '{cursor}'" if cursor else "")
        page = await _page(client, f"select {select} from records where {w} "
                                   f"order by start_timestamp asc limit {_PAGE}")
        rows.extend(page)
        if len(page) < _PAGE or not page[-1].get("ts"):
            return rows
        cursor = page[-1]["ts"]
        await asyncio.sleep(12)          # stay well under the per-minute org read limit


def _role_from_span(span_name: str) -> str:
    return "buyer" if span_name.startswith("buyer") else "seller"


def _parse_input_messages(raw: str) -> list[dict]:
    """pydantic-ai `gen_ai.input.messages` → ordered buyer/seller moves (system dropped)."""
    moves = []
    try:
        for m in json.loads(raw):
            role = {"user": "buyer", "assistant": "seller"}.get(m.get("role"))
            if not role:
                continue
            text = " ".join(p.get("content", "") for p in (m.get("parts") or [])
                            if p.get("type") == "text" and p.get("content")).strip()
            if text:
                moves.append({"role": role, "action": "counter", "offer": None, "text": text})
    except Exception:  # noqa: BLE001
        pass
    return moves


def _to_seconds(ts: str) -> float:
    """Crude ISO→epoch for ordering/window math (date+time to the second; tz assumed UTC)."""
    try:
        d, t = ts[:19].split("T")
        y, mo, da = (int(x) for x in d.split("-"))
        h, mi, s = (int(x) for x in t.split(":"))
        return (((y * 372 + mo * 31 + da) * 24 + h) * 60 + mi) * 60 + s
    except Exception:  # noqa: BLE001
        return 0.0


async def main() -> None:
    if not lr.configured():
        print("No LOGFIRE token configured. Nothing to recover.")
        return
    print(f"Recovering transcripts from Logfire ({lr._base()}) …")
    async with httpx.AsyncClient(timeout=60) as client:
        turns = await _paginate(client,
            "span_name, attributes->>'gambit.run_id' rid, attributes->>'action' action, "
            "attributes->>'offer' offer, attributes->>'text' text, start_timestamp ts",
            f"span_name in ({_TURN_SPANS})")
        print(f"  Tier A: {len(turns)} CLI turn spans")
        jobs = await _paginate(client,
            "attributes->>'gambit.run_id' rid, start_timestamp ts",
            "attributes->>'gambit.kind'='job' and attributes->>'gambit.source'='human'")
        # one scan for both browser span types (halves the query count vs scanning each separately)
        tier_b_rows = await _paginate(client,
            "span_name, attributes->>'gen_ai.conversation.id' conv, attributes->>'final_result' final_result, "
            "attributes->>'gen_ai.input.messages' msgs, start_timestamp ts",
            "span_name in ('agent run','chat MiniMax-M3') and attributes ? 'gen_ai.conversation.id'")
        agent_runs = [r for r in tier_b_rows if r.get("span_name") == "agent run"]
        chats = [r for r in tier_b_rows if r.get("span_name") == "chat MiniMax-M3"]
        print(f"  Tier B: {len(agent_runs)} agent-run + {len(chats)} chat spans")

    # --- Tier A: exact moves by run_id ---
    tier_a: dict[str, list[dict]] = {}
    for r in turns:
        rid = r.get("rid")
        if not rid:
            continue
        tier_a.setdefault(rid, []).append({
            "role": _role_from_span(r["span_name"]), "action": r.get("action") or "counter",
            "offer": lr._f(r.get("offer")), "text": (r.get("text") or "").strip(), "_ts": r.get("ts")})
    for moves in tier_a.values():
        moves.sort(key=lambda m: m.get("_ts") or "")
        for m in moves:
            m.pop("_ts", None)

    # --- Tier B: rebuild each conversation, then map conv → run_id by time ---
    conv_latest_chat: dict[str, tuple[str, str]] = {}      # conv -> (ts, msgs) of the latest chat span
    conv_latest_reply: dict[str, tuple[str, str]] = {}     # conv -> (ts, final_result)
    conv_span_ts: dict[str, list[float]] = {}
    for r in chats:
        conv, ts = r.get("conv"), r.get("ts")
        if not conv or not r.get("msgs"):
            continue
        conv_span_ts.setdefault(conv, []).append(_to_seconds(ts))
        if conv not in conv_latest_chat or ts > conv_latest_chat[conv][0]:
            conv_latest_chat[conv] = (ts, r["msgs"])
    for r in agent_runs:
        conv, ts = r.get("conv"), r.get("ts")
        if not conv:
            continue
        conv_span_ts.setdefault(conv, []).append(_to_seconds(ts))
        if r.get("final_result") and (conv not in conv_latest_reply or ts > conv_latest_reply[conv][0]):
            conv_latest_reply[conv] = (ts, r["final_result"])

    tier_b: dict[str, list[dict]] = {}
    for conv, (_ts, msgs) in conv_latest_chat.items():
        moves = _parse_input_messages(msgs)
        reply = conv_latest_reply.get(conv)
        if reply and (not moves or moves[-1]["text"] != reply[1].strip()):
            moves.append({"role": "seller", "action": "counter", "offer": None, "text": reply[1].strip()})
        if moves:
            tier_b[conv] = moves

    # run_id → its job-span times (browser human runs), for temporal mapping
    job_times: dict[str, list[float]] = {}
    for j in jobs:
        if j.get("rid") and j.get("ts"):
            job_times.setdefault(j["rid"], []).append(_to_seconds(j["ts"]))

    conv_to_run: dict[str, str] = {}
    for conv, secs in conv_span_ts.items():
        c0 = min(secs)
        best, best_d = None, _MAP_WINDOW_S
        for rid, jts in job_times.items():
            d = min(abs(c0 - t) for t in jts)
            if d < best_d:
                best, best_d = rid, d
        if best:
            conv_to_run[conv] = best

    # --- merge into the durable store ---
    store = history.get_history()
    details = history.export_all(store)
    a_recovered = b_recovered = b_new = 0

    for rid, moves in tier_a.items():
        d = details.get(rid)
        if d is None:
            d = {"run_id": rid, "title": "chat (CLI, recovered)", "source": "human",
                 "category": "human-vs-agent", "moves": [], "outcomes": [], "reflections": [],
                 "curve": [], "ts": moves and None}
            details[rid] = d
        if not d.get("moves"):
            d["moves"] = moves
            a_recovered += 1

    used_convs = set()
    for conv, rid in conv_to_run.items():
        d = details.get(rid)
        if d is not None and not d.get("moves") and conv in tier_b:
            d["moves"] = tier_b[conv]
            d["title"] = d.get("title") or "chat: browser haggle (recovered)"
            used_convs.add(conv)
            b_recovered += 1

    for conv, moves in tier_b.items():           # conversations we couldn't map to a run → keep standalone
        if conv in used_convs:
            continue
        rid = f"recovered-{conv[:12]}"
        if rid not in details:
            details[rid] = {"run_id": rid, "title": "chat: browser haggle (recovered, unmapped)",
                            "source": "human", "category": "human-vs-agent", "moves": moves,
                            "outcomes": [], "reflections": [], "curve": []}
            b_new += 1

    pairs = [(history.summarize(rid, d), d) for rid, d in details.items()]
    store.bulk_replace(pairs)

    print(f"\nDone → {type(store).__name__}.")
    print(f"  Tier A (CLI, exact):        {a_recovered} runs given transcripts")
    print(f"  Tier B (browser, mapped):   {b_recovered} runs given transcripts")
    print(f"  Tier B (browser, unmapped): {b_new} stored standalone as recovered-*")
    print(f"  total runs in store:        {len(pairs)}")


if __name__ == "__main__":
    asyncio.run(main())
